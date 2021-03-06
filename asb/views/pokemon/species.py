import collections
import itertools

from pyramid.view import view_config
import sqlalchemy as sqla

from asb import db
from asb.resources import SpeciesIndex

def or_iter():
    """A simple iterator to join evolution criteria with "OR", without having
    to make a list.  (Not making a list means we can use the link() def from
    helpers.mako.)
    """

    yield ''

    while True:
        yield ' <em>OR</em> '

def show_form_evo(form):
    """Determine whether to show this Pokémon form's evolution method
    separately.
    """

    # XXX Sighhhh I'd like to not special-case this someday
    return (form.is_default or form.identifier.endswith('-alola') or
            form.species.identifier == 'meowstic')

@view_config(context=SpeciesIndex, renderer='/indices/pokemon_species.mako')
def species_index(context, request):
    """The index page for all the species of Pokémon.

    (Forms, actually.  Whatever.)
    """

    # A subquery to count how many of each Pokémon form there are in the league
    population_subquery = (
        db.DBSession.query(db.Pokemon.pokemon_form_id,
            sqla.func.count('*').label('population'))
        .select_from(db.Pokemon)
        .filter(db.Pokemon.is_active())
        .group_by(db.Pokemon.pokemon_form_id)
        .subquery()
    )

    # Get all the Pokémon and population counts.  Making this an OrderedDict
    # means we can just pass it to pokemon_form_table as is.
    pokemon = collections.OrderedDict(
        db.DBSession.query(db.PokemonForm,
            population_subquery.c.population)
        .select_from(db.PokemonForm)
        .join(db.PokemonSpecies)
        .outerjoin(population_subquery)
        .options(
             sqla.orm.joinedload('species'),
             sqla.orm.subqueryload('abilities'),
             sqla.orm.subqueryload('abilities.ability'),
             sqla.orm.subqueryload('types')
        )
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

    # Figure out type matchups
    type_matchups = collections.OrderedDict([
        (2, ('Very weak to (2×)', [])),
        (1, ('Weak to (1.5×)', [])),
        (-1, ('Resistant to (0.67×)', [])),
        (-2, ('Very resistant to (0.5×)', [])),
        (None, ('Immune to (0×)', []))
    ])

    if len(pokemon.types) == 1:
        del type_matchups[2]
        del type_matchups[-2]

    zipped_matchups = zip(
        *(type_.defending_matchups for type_ in pokemon.types)
    )

    for matchups in zipped_matchups:
        type_ = matchups[0].attacking_type
        result = 0

        for matchup in matchups:
            if matchup.result.identifier == 'super-effective':
                result += 1
            elif matchup.result.identifier == 'not-very-effective':
                result -= 1
            elif matchup.result.identifier == 'ineffective':
                result = None
                break

        if result != 0:
            type_matchups[result][1].append(type_)

    # Get this Pokémon's abilities but strip out the duplicates
    abilities = []
    for ability in pokemon.abilities:
        if ability.ability_id not in (a.ability_id for a in abilities):
            abilities.append(ability)


    # Build the evolution tree.  n.b. this algorithm assumes that all final
    # evolutions within a family are at the same evo stage.  I'd be surprised
    # if that ever stopped being true, though.

    family = pokemon.species.family

    # Start with all the final evolutions
    prevos = set(species.pre_evolution for species in family.species)
    finals = []

    for species in family.species:
        if species not in prevos:
            for form in species.forms:
                if show_form_evo(form):
                    finals.append(form)

    evo_tree = [finals]

    # Build backwards, with each pre-evo appearing "above" its evo.  Pokémon
    # with multiple evos (now or at a later stage) will appear multiple times.
    while evo_tree[0][0].species.evolves_from_species_id is not None:
        evo_tree.insert(0, [evo.pre_evolution_form for evo in evo_tree[0]])

    # Collapse each layer; for example, [A, A, B] would become [(A, 2), (B, 1)]
    for n, layer in enumerate(evo_tree):
        evo_tree[n] = [(evo, sum(1 for _ in group))
            for evo, group in itertools.groupby(layer)]


    # Find all the Pokémon of this species/form in the league
    census = (
        db.DBSession.query(db.Pokemon)
        .filter_by(pokemon_form_id=pokemon.id)
        .filter(db.Pokemon.is_active())
        .options(
             sqla.orm.joinedload('ability'),
             sqla.orm.joinedload('trainer'),
             sqla.orm.joinedload('gender')
        )
        .order_by(db.Pokemon.name)
        .all()
    )

    return {
        'pokemon': pokemon,
        'abilities': abilities,
        'type_matchups': type_matchups,
        'evo_tree': evo_tree,
        'or_iter': or_iter,
        'census': census
    }
