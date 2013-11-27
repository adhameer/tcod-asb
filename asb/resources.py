"""Define all the resources and the traversal tree."""

from sqlalchemy.orm.exc import NoResultFound

import asb.models as models

class Root(dict):
    """A root resource."""
    __name__ = None
    __parent__ = None

class DexIndex:
    """A resource for anything in the database whose info you'd want to look
    up.
    """

    table = None

    def __getitem__(self, identifier):
        """Get the requested resource from the database."""

        try:
            item = (models.DBSession.query(self.table)
                .filter_by(identifier=identifier)
                .one())
        except NoResultFound:
            raise KeyError

        return item

class TrainerIndex(DexIndex):
    __name__ = 'trainers'
    table = models.Trainer

class PokemonIndex(DexIndex):
    __name__ = 'pokemon'
    table = models.Pokemon

class SpeciesIndex(DexIndex):
    """Actually a form index."""
    __name__ = 'species'
    table = models.PokemonForm

class MoveIndex(DexIndex):
    __name__ = 'moves'
    table = models.Move

class AbilityIndex(DexIndex):
    __name__ = 'abilities'
    table = models.Ability

class ItemIndex(DexIndex):
    __name__ = 'items'
    table = models.Item


def get_root(request):
    root = Root({
        'trainers': TrainerIndex(),
        'pokemon': PokemonIndex(),
        'species': SpeciesIndex(),
        'moves': MoveIndex(),
        'abilities': AbilityIndex(),
        'items': ItemIndex()
    })
    
    for index in root.values():
        index.__parent__ = root

    return root
