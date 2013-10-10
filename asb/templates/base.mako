<%
    from asb.views.user import LoginForm
    login_form = LoginForm()
%>\
\
<!DOCTYPE html>
<html>
<head>
    <title><%block name='title'>The Cave of Dragonflies ASB</%block></title>
    <link rel="stylesheet" href="/static/asb.css">
</head>
<body>
<section id="header">
<p style="text-align: center; margin: 0; padding: 2em; color: white;">
  banner goes here once I make it
</p>

<div id="menu">
<ul id="menu-user">
% if False:  ## if logged in
  <li>Account stuff</li>
  <li>Buy stuff</li>
  <li>idk</li>
  <li>Log out</li>
% else:
  <li id="register"><a href="/register">Register</a></li>
  <li>
    <form action="/login" method="POST" id="login">
      ${login_form.username.label() | n} ${login_form.username() | n}
      ${login_form.password.label() | n} ${login_form.password() | n}
      ${login_form.log_in() | n}
    </form>
  </li>
% endif
</ul>

<ul id="menu-dex">
  <li><a href="/trainers">Trainers</a></li>
  <li><a href="/pokemon">Pokémon</a></li>
  <li><a href="/pokemon/species">Species</a></li>
  <li>Items</li>
  <li>Moves?</li>
  <li>Abilities?</li>
</ul>
</div>
</section>

<section id="body">
${next.body()}\
</section>
</body>
</html>
