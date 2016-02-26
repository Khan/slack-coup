slack-coup
==========

A bot to play Coup in Slack.

Coup is copyright [Indie Boards & Cards](http://www.indieboardsandcards.com/).  We love them and you should [buy the game](http://www.amazon.com/Indie-Boards-Cards-COU1IBC-Dystopian/dp/B00GDI4HX4).

Deploying
---------
To deploy your own, create a Google App Engine project, set `PROJECT` in the `Makefile`, and `make deploy`.  Set up a slash command in Slack, pointed at `https://<whatever>.appspot.com`.
