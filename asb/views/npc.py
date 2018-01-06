from pyramid.view import view_config
import sqlalchemy as sqla
import sqlalchemy.orm

from asb import db
from asb.resources import NPCIndex

@view_config(context=NPCIndex, renderer='/indices/npcs.mako')
def npc_index(context, request):
    """The index of all the NPCs in the league."""

    pokemon_count = (
        db.DBSession.query(db.Pokemon.trainer_id, sqla.func.count('*')
            .label('count'))
        .select_from(db.Pokemon)
        .filter(db.Pokemon.is_npc())
        .group_by(db.Pokemon.trainer_id)
        .subquery()
    )

    trainers = (
        db.DBSession.query(db.Trainer, pokemon_count.c.count)
        .select_from(db.Trainer)
        .filter(db.Trainer.is_npc())
        .join(pokemon_count, pokemon_count.c.trainer_id == db.Trainer.id)
        .options(sqla.orm.subqueryload('squad'))
        .order_by(db.Trainer.name)
        .all()
    )

    return {'trainers': trainers}
