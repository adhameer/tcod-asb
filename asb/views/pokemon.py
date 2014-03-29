from collections import OrderedDict
import itertools

import pyramid.httpexceptions as httpexc
from pyramid.view import view_config
from sqlalchemy import func
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import select
import transaction
import wtforms

from asb import db
from asb.resources import PokemonIndex, SpeciesIndex
from asb.forms import CSRFTokenForm, MultiCheckboxField

class EditPokemonForm(CSRFTokenForm):
    """A form for editing a Pokémon.

    This will mean more than just its nickname, eventually.
    """

    name = wtforms.TextField('Name')
    save = wtforms.SubmitField('Save')

class PokemonMovingForm(CSRFTokenForm):
    """A form for selecting Pokémon to deposit or withdraw.

    Several parts of this form must be created dynamically, using
    pokemon_deposit_form or pokemon_withdraw_form (below).
    """

    pokemon = MultiCheckboxField(coerce=int)
    submit = wtforms.SubmitField()

class PokemonSpeciesField(wtforms.StringField):
    """A field for a Pokémon species that also fetches the corresponding
    species from the database, and makes sure that it's buyable, for Quick Buy.

    When I get lookup working, it will replace this.
    """

    def _value(self):
        if self.data:
            return self.data[0]
        else:
            return ''

    def process_data(self, value):
        """"""

        if value is None:
            self.data = ('', None)
        else:
            self.data = (value.name, value)

    def process_formdata(self, valuelist):
        name, = valuelist

        try:
            identifier = db.identifier(name)
        except ValueError:
            # Reduces to empty identifier; obviously not going to be a species
            self.data = (name, None)
            return

        # Deal with the Nidorans
        if identifier in ('nidoran-female', 'nidoranf'):
            identifier = 'nidoran-f'
        elif identifier in ('nidoran-male', 'nidoranm'):
            identifier = 'nidoran-m'

        # Try to fetch the species
        try:
            species = (db.DBSession.query(db.PokemonSpecies)
                .filter_by(identifier=identifier)
                .options(joinedload('default_form'))
                .one()
            )

            self.data = (name, species)
        except NoResultFound:
            self.data = (name, None)

    def pre_validate(self, form):
        """Make sure that we actually found a buyable species."""

        name, species = self.data
        if species is None:
            raise wtforms.validators.ValidationError('No such Pokémon found')
        elif species.rarity is None or species.is_fake:
            raise wtforms.validators.ValidationError(
                "{0} isn't buyable".format(species.name))

class PokemonCheckoutForm(CSRFTokenForm):
    """A form for actually buying all the Pokémon in the trainer's cart.

    The Pokémon subforms must be created dynamically, using the method
    pokemon_checkout_form (below).
    """

    submit = wtforms.SubmitField('Done')

class QuickBuyForm(CSRFTokenForm):
    """A form for typing in the name of a Pokémon to buy."""

    pokemon = PokemonSpeciesField('Quick buy')
    quickbuy = wtforms.SubmitField('Go!')

def pokemon_deposit_form(trainer, request, use_post=True):
    """Return a PokemonMovingForm for depositing Pokémon."""

    post = request.POST if use_post else None
    form = PokemonMovingForm(post, csrf_context=request.session)

    form.pokemon.choices = [(p.id, '') for p in trainer.squad]

    # The Length validator is intended for strings, but this works so whatever
    form.pokemon.validators.append(
        wtforms.validators.Length(max=len(trainer.squad) - 1,
            message='You must keep at least one Pokémon in your active squad')
    )

    form.submit.label = wtforms.fields.Label('submit', 'Deposit')

    return form

def pokemon_withdraw_form(trainer, request, use_post=True):
    """Return a PokemonMovingForm for withdrawing Pokémon."""

    post = request.POST if use_post else None
    form = PokemonMovingForm(post, csrf_context=request.session)

    form.pokemon.choices = [(p.id, '') for p in trainer.pc]

    if form.pokemon.data:
        # We want to tell them how many Pokémon they're over by if they try to
        # withdraw too many, which means we have to add this validator when the
        # form is being submitted.  Thankfully, that's exactly when we need it.
        max_withdraws = 10 - len(trainer.squad)
        overflow = len(form.pokemon.data) - max_withdraws

        if max_withdraws == 0:
            message = 'Your squad is full!'
        else:
            message = ('You only have room in your squad to withdraw {0} more '
                'Pokémon; please uncheck at least {1}'.format(max_withdraws,
                overflow))

        form.pokemon.validators.append(wtforms.validators.Length(
            max=max_withdraws, message=message))

    form.submit.label = wtforms.fields.Label('submit', 'Withdraw')

    return form

def pokemon_checkout_form(cart, request):
    """Return a PokemonCheckoutForm based on the given cart."""

    class ContainerForm(wtforms.Form):
        """A container for all the Pokémon subforms."""

        pass

    total = 0

    # Keep track of how many of each species we've seen so far, in case they're
    # buying more than one of something
    species_seen = {}

    # Now for all the subforms.  We're going to need to set the name species in
    # a class in a moment, hence the underscore on this one.
    for species_ in cart:
        species_ = db.DBSession.merge(species_)
        species_seen.setdefault(species_.identifier, 0)
        species_seen[species_.identifier] += 1
        n = species_seen[species_.identifier]

        # Figure out ability choices
        abilities = [(ability.slot, ability.ability.name)
            for ability in species_.default_form.abilities
            if not ability.is_hidden]

        if species_.identifier == 'basculin':
            # Fuck it, this is the only buyable Pokémon it matters for
            abilities[0] = (1, 'Reckless (Red)/Rock Head (Blue)')

        # Figure out Pokémon form choices
        # XXX At some point in the future we'll actually have to look at what
        # the condition is
        forms = [form for form in species_.forms if form.condition is None]

        class Subform(wtforms.Form):
            """A subform for setting an individual Pokémon's info at checkout.

            Has fields for name, gender, ability, and form (as in e.g. West vs
            East Shellos), but any combination of the last three fields may be
            omitted if they'd only have one option.
            """

            name_ = wtforms.TextField('Name', default=species_.name)

            # Gender field, if the Pokémon can be more than one gender
            if len(species_.genders) > 1:
                gender = wtforms.SelectField('Gender', coerce=int,
                    choices=[(1, 'Female'), (2, 'Male')], default=1)

            # Ability field, if the Pokémon can have more than one ability
            if len(abilities) > 1:
                ability = wtforms.SelectField('Ability', coerce=int,
                    choices=abilities, default=1)

            # Form field, if the Pokémon has different forms
            if len(forms) > 1:
                form_ = wtforms.SelectField('Form', coerce=int,
                    choices=[(f.id, f.form_name or 'Default') for f in forms],
                    default=species_.default_form.id)

            species = species_  # Hang on to this; we'll need it
            number = n  # This too

        # Add this subform to the container form
        if n > 1:
            subform_name = '{0}-{1}'.format(species_.identifier, n)
        else:
            subform_name = species_.identifier

        setattr(ContainerForm, subform_name, wtforms.FormField(Subform))

    # Create the form!
    class Form(PokemonCheckoutForm):
        pokemon = wtforms.FormField(ContainerForm)

    form = Form(request.POST, csrf_context=request.session)

    return form

@view_config(context=PokemonIndex, renderer='/indices/pokemon.mako')
def pokemon_index(context, request):
    """The index page for everyone's Pokémon."""

    pokemon = (
        db.DBSession.query(db.Pokemon)
        .filter_by(unclaimed_from_hack=False)
        .join(db.PokemonForm)
        .join(db.PokemonSpecies)
        .order_by(db.PokemonSpecies.order, db.Pokemon.name)
        .options(
            joinedload('gender'),
            joinedload('trainer'),
            joinedload('form'),
            joinedload('form.species'),
            joinedload('ability'),
            joinedload('item')
        )
        .all()
    )

    return {'pokemon': pokemon}

@view_config(context=db.Pokemon, renderer='/pokemon.mako')
def pokemon(context, request):
    """An individual Pokémon's info page."""

    return {'pokemon': context}

@view_config(name='edit', context=db.Pokemon, permission='edit:basics',
  request_method='GET', renderer='edit_pokemon.mako')
def edit_pokemon(pokemon, request):
    form = EditPokemonForm(csrf_context=request.session)
    form.name.data = pokemon.name

    return {'pokemon': pokemon, 'form': form}

@view_config(name='edit', context=db.Pokemon, permission='edit:basics',
  request_method='POST', renderer='edit_pokemon.mako')
def edit_pokemon_commit(pokemon, request):
    form = EditPokemonForm(request.POST, csrf_context=request.session)

    if not form.validate():
        return {'pokemon': pokemon, 'form': form}

    pokemon.name = form.name.data
    pokemon.update_identifier()
    db.DBSession.flush()

    return httpexc.HTTPSeeOther(request.resource_url(pokemon))

@view_config(name='manage', context=PokemonIndex, permission='manage-account',
  request_method='GET', renderer='/manage/pokemon.mako')
def manage_pokemon(context, request):
    """A page for depositing and withdrawing one's Pokémon."""

    trainer = request.user

    if trainer.squad:
        deposit = pokemon_deposit_form(trainer, request)
    else:
        deposit = None

    if trainer.pc:
        withdraw = pokemon_withdraw_form(trainer, request)
    else:
        withdraw = None

    return {'trainer': trainer, 'deposit': deposit, 'withdraw': withdraw}

@view_config(name='manage', context=PokemonIndex, permission='manage-account',
  request_method='POST', renderer='/manage/pokemon.mako')
def manage_pokemon_commit(context, request):
    """Process a request to deposit or withdraw Pokémon."""

    trainer = request.user

    if request.POST['submit'] == 'Deposit':
        deposit = pokemon_deposit_form(trainer, request)
        withdraw = pokemon_withdraw_form(trainer, request, use_post=False)
        form = deposit
        is_in_squad = False
    elif request.POST['submit'] == 'Withdraw':
        deposit = pokemon_deposit_form(trainer, request, use_post=False)
        withdraw = pokemon_withdraw_form(trainer, request)
        form = withdraw
        is_in_squad = True

    if not form.validate():
        return {'trainer': trainer, 'deposit': deposit, 'withdraw': withdraw}

    to_toggle = (db.DBSession.query(db.Pokemon)
        .filter(db.Pokemon.id.in_(form.pokemon.data))
        .all())

    for pokemon in to_toggle:
        pokemon.is_in_squad = is_in_squad

    return httpexc.HTTPSeeOther('/pokemon/manage')

def get_rarities():
    """Fetch all the rarities and all the info we'll need about their Pokémon
    for the "buy Pokémon" page.
    """

    return (db.DBSession.query(db.Rarity)
        .options(
            subqueryload('pokemon_species'),
            subqueryload('pokemon_species.default_form'),
            subqueryload('pokemon_species.default_form.types'),
            subqueryload('pokemon_species.default_form.abilities'),
            subqueryload('pokemon_species.default_form.abilities.ability')
        )
        .order_by(db.Rarity.id)
        .all())

@view_config(route_name='pokemon.buy', permission='manage-account',
  request_method='GET', renderer='/buy/pokemon.mako')
def buy_pokemon(context, request):
    """A page for buying Pokémon."""

    quick_buy = QuickBuyForm(csrf_context=request.session)
    rarities = get_rarities()
    cart = request.session.get('cart', [])

    return {'rarities': rarities, 'quick_buy': quick_buy, 'cart': cart}

@view_config(route_name='pokemon.buy', permission='manage-account',
  request_method='POST', renderer='/buy/pokemon.mako')
def buy_pokemon_process(context, request):
    """Process a request to quick-buy a Pokémon, add one to the user's cart, or
    remove one from the user's cart.
    """

    quick_buy = None

    if 'quickbuy' in request.POST:
        # Quick buy (well, more like quick add-to-cart)
        quick_buy = QuickBuyForm(request.POST, csrf_context=request.session)

        if quick_buy.validate():
            species = quick_buy.pokemon.data[1]
            request.session.setdefault('cart', []).append(species)
            return httpexc.HTTPSeeOther('/pokemon/buy')
    elif 'add' in request.POST:
        # Add to cart
        identifier = request.POST['add']

        # Make sure it's a real, buyable Pokémon
        try:
            species = (db.DBSession.query(db.PokemonSpecies)
                .filter_by(identifier=identifier)
                .options(joinedload('rarity'), joinedload('default_form'))
                .one()
            )
        except NoResultFound:
            # The only way something can go wrong here is if someone's mucking
            # around, so I don't really care about figuring out errors
            pass
        else:
            if not (species.rarity_id is None or species.is_fake):
                # Valid Pokémon; add it to the cart
                request.session.setdefault('cart', []).append(species)
                return httpexc.HTTPSeeOther('/pokemon/buy')
    elif 'remove' in request.POST and 'cart' in request.session:
        # Remove from cart
        identifier = request.POST['remove']

        # Go through and find the Pokémon they want to remove
        for n, pokemon in enumerate(request.session['cart']):
            if pokemon.identifier == identifier:
                request.session['cart'].pop(n)
                return httpexc.HTTPSeeOther('/pokemon/buy')

        # Again, if they're trying to buy something that's not in their cart,
        # who cares?  Let them quietly fall back to the buy page.

    # If we haven't returned yet, something's gone wrong; back to the buy page

    if quick_buy is None:
        quick_buy = QuickBuyForm(csrf_context=request.session)

    rarities = get_rarities()
    cart = request.session.get('cart', [])

    return {'rarities': rarities, 'quick_buy': quick_buy, 'cart': cart}

@view_config(route_name='pokemon.buy.checkout', permission='manage-account',
  request_method='GET', renderer='/buy/pokemon_checkout.mako')
def pokemon_checkout(context, request):
    """A page for actually buying all the Pokémon in the trainer's cart."""

    # Make sure they actually have something to check out
    if 'cart' not in request.session or not request.session['cart']:
        request.session.flash('Your cart is empty')
        return httpexc.HTTPSeeOther('/pokemon/buy')

    # Make sure they can afford everything
    grand_total = sum(pkmn.rarity.price for pkmn in request.session['cart'])
    if grand_total > request.user.money:
        request.session.flash("You can't afford all that!")
        return httpexc.HTTPSeeOther('/pokemon/buy')

    # And go
    form = pokemon_checkout_form(request.session['cart'], request)

    return {'form': form}

@view_config(route_name='pokemon.buy.checkout', permission='manage-account',
  request_method='POST', renderer='/buy/pokemon_checkout.mako')
def pokemon_checkout_commit(context, request):
    """Process a checkout form and actually give the user their new Pokémon."""

    trainer = request.user

    # Make sure they actually, uh, have something to buy
    if 'cart' not in request.session or not request.session['cart']:
        request.session.flash('Your cart is empty')
        return httpexc.HTTPSeeOther('/pokemon/buy')

    # Make sure they actually have enough money
    grand_total = sum(pkmn.rarity.price for pkmn in request.session['cart'])
    if grand_total > trainer.money:
        request.session.flash("You can't afford all that!")
        return httpexc.HTTPSeeOther('/pokemon/buy')

    # Double-check their checkout form
    form = pokemon_checkout_form(request.session['cart'], request)

    if not form.validate():
        return {'form': form}

    # Okay this is it.  Time to actually create these Pokémon.
    squad_count = len(trainer.squad)

    for subform in form.pokemon:
        # Get the next available ID for this Pokémon
        nextval = db.Pokemon.pokemon_id_seq.next_value()
        id, = db.DBSession.execute(select([nextval])).fetchone()

        # Figure out form/gender/ability
        if hasattr(subform, 'form_'):
            form_id = subform.form_.data
        else:
            form_id = subform.species.default_form.id

        if hasattr(subform, 'gender'):
            gender_id = subform.gender.data
        else:
            gender_id = subform.species.genders[0].id

        if hasattr(subform, 'ability'):
            ability_slot = subform.ability.data
        else:
            ability_slot = 1

        # Plop it in the squad if there's still room
        to_squad = squad_count < 10
        squad_count += to_squad

        # Aaaaand create it.
        pokemon = db.Pokemon(
            id=id,
            identifier='temp-{0}'.format(subform.name_.data),
            name=subform.name_.data,
            pokemon_form_id=form_id,
            gender_id=gender_id,
            trainer_id=trainer.id,
            is_in_squad=to_squad,
            ability_slot=ability_slot
        )

        db.DBSession.add(pokemon)
        pokemon.update_identifier()

    # Finish up and return to the "Your Pokémon" page
    trainer.money -= grand_total
    del request.session['cart']

    return httpexc.HTTPSeeOther('/pokemon/manage')

@view_config(context=SpeciesIndex, renderer='/indices/pokemon_species.mako')
def species_index(context, request):
    """The index page for all the species of Pokémon.

    (Forms, actually.  Whatever.)
    """

    # A subquery to count how many of each Pokémon form there are in the league
    population_subquery = (
        db.DBSession.query(db.Pokemon.pokemon_form_id,
            func.count('*').label('population'))
        .select_from(db.Pokemon)
        .filter(db.Pokemon.unclaimed_from_hack == False)
        .group_by(db.Pokemon.pokemon_form_id)
        .subquery()
    )

    # Get all the Pokémon and population counts.  Making this an OrderedDict
    # means we can just pass it to pokemon_form_table as is.
    pokemon = OrderedDict(
        db.DBSession.query(db.PokemonForm,
            population_subquery.c.population)
        .select_from(db.PokemonForm)
        .join(db.PokemonSpecies)
        .outerjoin(population_subquery)
        .options(
             joinedload('species'),
             subqueryload('abilities'),
             subqueryload('abilities.ability'),
             subqueryload('types')
        )
        .filter(db.PokemonSpecies.is_fake == False)
        .order_by(db.PokemonForm.order)
        .all()
    )

    return {'pokemon': pokemon}

@view_config(context=db.PokemonForm, renderer='/pokemon_species.mako')
def species(pokemon, request):
    """The dex page of a Pokémon species.

    Under the hood, this is actually the dex page for a form.  But it's clearer
    to present it as the page for a species and pretend the particular form is
    just a detail.
    """

    # Build the evolution tree.  n.b. this algorithm assumes that all final
    # evolutions within a family are at the same evo stage.  I'd be surprised
    # if that ever stopped being true, though.

    family = pokemon.species.family

    # Start with all the final evolutions
    prevos = set(species.pre_evolution for species in family.species)
    finals = [pokemon for pokemon in family.species if pokemon not in prevos]
    evo_tree = [finals]

    # Build backwards, with each pre-evo appearing "above" its evo.  Pokémon
    # with multiple evos (now or at a later stage) will appear multiple times.
    while evo_tree[0][0].evolves_from_species_id is not None:
        evo_tree.insert(0, [evo.pre_evolution for evo in evo_tree[0]])

    # Collapse each layer; for example, [A, A, B] would become [(A, 2), (B, 1)]
    for n, layer in enumerate(evo_tree):
        evo_tree[n] = [(evo, sum(1 for _ in group))
            for evo, group in itertools.groupby(layer)]

    return {'pokemon': pokemon, 'evo_tree': evo_tree}
