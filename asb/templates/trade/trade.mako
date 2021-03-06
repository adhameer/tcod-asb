<%inherit file='/base.mako'/>\
<%namespace name="h" file="/helpers/helpers.mako"/>\
<%namespace name="t" file="/helpers/tables.mako"/>\
<%block name="title">Trade #${trade.id} - The Cave of Dragonflies ASB</%block>\

<% from asb.markdown import md, chomp %>

% for lot in trade.lots:
    % if request.has_permission('trade.lot.view', lot):
        % if lot.sender == request.user:
            % if lot.state == 'draft':
                <h1>Confirm your gift</h1>
            % else:
                <h1>Your gift</h1>
            % endif
        % elif lot.recipient == request.user:
            <h1>A gift from ${lot.sender.name}</h1>
        % else:
            <h1>A gift from ${lot.sender.name} to ${lot.recipient.name}</h1>
        % endif

        % if lot.state == 'draft':
            <p>Please confirm that the information below is correct.  This
            offer has not been made yet.  However, anything included has been
            withdrawn from your account, and will be returned if the trade is
            cancelled or rejected.</p>
        % endif

        <p>
            % if lot.sender == request.user:
            You offered
            % else:
            ${lot.sender.name} offered
            % endif

            % if lot.money is None:
            the following:
            % elif lot.pokemon or lot.items:
            <b>$${lot.money}</b> and the following:
            % else:
            <b>$${lot.money}</b>.
            % endif
        </p>

        <% items = lot.grouped_items() %>
        % if items:
            <h2>Items</h2>
            <table class="standard-table effect-table">
            <col class="icon item-icon">
            <col class="item">
            <col class="stat">
            <col class="summary">
            <thead>
                <tr>
                    <th colspan="2">Item</th>
                    <th><abbr title="Quantity">Qty</th>
                    <th>Summary</th>
                </tr>
            </thead>
            <tbody>
                % for (item, qty) in items:
                    <tr>
                        <td class="icon item-icon">
                            <img src="/static/images/items/${item.identifier}.png"
                                 alt="">
                        </td>
                        <td class="focus-column">${h.link(item)}</td>
                        <td class="stat">${qty}</td>
                        <td>${item.summary | md.convert, chomp, n}</td>
                    </tr>
                % endfor
            </tbody>
            </table>
        % endif

        % if lot.pokemon:
            <h2>Pokémon</h2>
            ${t.pokemon_table(lot.pokemon, skip_cols=['trainer'])}
        % endif

        % if lot.sender == request.user:
            % if lot.state == 'draft':
                <form action="${request.path}" method="POST">
                    ${h.form_error_list(*confirm_form.errors.values())}
                    ${confirm_form.csrf_token}
                    ## ${confirm_form.edit}
                    ${confirm_form.confirm}
                    ${confirm_form.cancel}
                </form>
            % elif lot.state == 'proposed':
                <h1>Reconsider</h2>

                <p>Your gift has not been accepted or declined yet.  You can
                still return it to the draft stage or cancel it altogether.</p>

                <form action="${request.path}" method="POST">
                    ${h.form_error_list(*reconsider_form.errors.values())}
                    ${reconsider_form.csrf_token}
                    ${reconsider_form.draft}
                    ${reconsider_form.cancel}
                </form>
            % endif
        % elif lot.recipient == request.user:
            % if lot.state == 'proposed':
                <h1>Accept this gift</h1>
                <form action="${request.path}" method="POST">
                    ${accept_form.csrf_token}
                    ${h.form_error_list(accept_form.csrf_token.errors,
                                        accept_form.accept.errors)}

                    <p>${accept_form.accept}</p>


                    <h2>Decline</h2>

                    ${h.form_error_list(accept_form.really_decline.errors,
                                        accept_form.decline.errors)}

                    <p>${accept_form.really_decline}
                    ${accept_form.really_decline.label.text}</p>

                    <p>${accept_form.decline}</p>
                </form>
            % endif
        % endif
    % endif
% endfor
