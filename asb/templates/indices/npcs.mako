<%inherit file='/base.mako'/>\
<%namespace name="h" file="/helpers/helpers.mako"/>\
<%block name='title'>NPCs - The Cave of Dragonflies ASB</%block>\

<table>
<thead>
    <tr>
        <th>Name</th>
        <th>Pkmn</th>
        <th>Active Squad</th>
    </tr>
</thead>

<tbody>
    % for trainer, pokemon_count in trainers:
    <tr>
        <td class="focus-column">${h.link(trainer)}</td>
        <td class="stat">${pokemon_count}</td>
        <td class="squad">
            % for pokemon in trainer.squad:
<a href="${request.resource_url(pokemon.__parent__, pokemon.__name__)}">\
${h.pokemon_icon(pokemon)}\
</a>\
            % endfor
        </td>
    </tr>
    % endfor
</tbody>
</table>
