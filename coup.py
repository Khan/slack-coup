import json
import logging

import webapp2
from google.appengine.ext import ndb

import engine


def deal_cards(existing_game, game_id, players):
    if existing_game and not existing_game.winner():
        raise engine.Misplay("There's already a game running in this room!  "
                             "To cancel it and start a new one, "
                             "`/coup restart [usernames]`.")
    game = engine.GameState.create(players)
    game.put()
    return {
        'response_type': 'in_channel',
        'text': "%s, get ready for a game of Coup!  Use `/coup cards` to view "
                "your cards, and `/coup action <action>` to take an action.  "
                "@%s, it's your turn." % (game.mention_all(), players[0])
    }


def cancel_game(game):
    game.delete()
    return {
        'response_type': 'in_channel',
        'text': "Game over, everyone loses.  To start a new game, "
                "`/coup deal`.",
    }


# TODO(benkraft): don't hardcode that it's `/coup`, use whatever it was called
# with.
@ndb.transactional
def run_command(game, game_id, username, args):
    if not args:
        # TODO(benkraft): return help
        raise engine.Misplay("What do you want to do?")
    # These don't need an existing game or a player.
    if args[0] in ('deal', 'new'):
        return deal_cards(game, game_id, args[1:])
    elif args[0] == 'restart':
        if game:
            cancel_game(game)
        return deal_cards(None, game_id, args[1:])

    # These need a game, but not a player.
    if not game:
        raise engine.Misplay("There's no game running in this channel.  "
                             "To start a new game, `/coup deal`.")
    elif args[0] == 'cancel':
        return cancel_game(game)
    elif args[0] in ('view', 'board'):
        return {
            'response_type': 'ephemeral',
            'text': game.status_view(),
        }
    elif args[0] in ('status', 'state'):
        return {
            'response_type': 'in_channel',
            'text': game.status_view(),
        }

    # These need a game and a player.
    # TODO: fake being another user for testing
    player = game.get_player(username)
    if not player:
        raise engine.Misplay("You're not in this game!  To start a new game, "
                             "`/coup deal`.")
    elif args[0] in ('cards', 'money', 'me', 'look'):
        return {
            'response_type': 'ephemeral',
            'text': player.view(public=False)
        }

    elif args[0] in ('action', 'act', 'do'):
        if len(args) == 2:
            target = None
        elif len(args) == 3:
            target = game.get_player(args[2])
            if not target:
                raise engine.Misplay("%s isn't playing!" % args[2])
        else:
            raise engine.Misplay("To take an action, "
                                 "`/coup action <action> [target]`.")
        return {
            'response_type': 'in_channel',
            'text': game.take_action(player, args[1], target)
        }
    elif args[0] in ('exchange', 'take'):
        return {
            'response_type': 'ephemeral',
            'text': game.take_cards(player),
        }
    elif args[0] == 'keep':
        if len(args) != 3:
            raise engine.Misplay("To complete an exchange, "
                                 "`/coup keep <card1> <card2>`.")
        return {
            'response_type': 'ephemeral',
            'text': game.keep_cards(player, args[1], args[2]),
        }
    elif args[0] in ('challenge', 'bullshit'):
        return {
            'response_type': 'in_channel',
            'text': game.pose_challenge(player),
        }
    elif args[0] == 'block':
        if len(args) != 2:
            raise engine.Misplay("To block, `/coup block <with_card>`.")
        return {
            'response_type': 'in_channel',
            'text': game.pose_block(player, args[1]),
        }

    # TODO(benkraft): merge various card-flipping actions for simplicity
    elif args[0] == 'show':
        if len(args) != 2:
            raise engine.Misplay("To flip a card in response to a challenge, "
                                 "`/coup show <card>`.")
        return {
            'response_type': 'in_channel',
            'text': game.resolve_challenge(player, args[1]),
        }
    elif args[0] == 'flip':
        if len(args) != 2:
            raise engine.Misplay("To lose a card from a failed challenge, "
                                 "`/coup flip <card>`.")
        return {
            'response_type': 'in_channel',
            'text': game.lose_challenge(player, args[1]),
        }
    elif args[0] == 'lose':
        if len(args) != 2:
            raise engine.Misplay("To lose a card due to an action, "
                                 "`/coup lose <card>`.")
        return {
            'response_type': 'in_channel',
            'text': game.lose_card(player, args[1]),
        }

    # TODO(benkraft): return help.
    raise engine.Misplay("I don't know of a command %s." % args[0])


class Command(webapp2.RequestHandler):
    def post(self):
        """Endpoint for the slash command."""
        # TODO(benkraft): check the token to prevent abuse?
        game_id = "%s#%s" % (self.request.POST['team_id'],
                             self.request.POST['channel_id'])
        game = engine.GameState.get_by_id(game_id)
        username = self.request.POST['user_name']
        args = self.request.POST['text'].split()
        try:
            answer = run_command(game, game_id, username, args)
            if args[0] not in ('deal', 'new', 'restart'):
                # Don't put the game if we didn't get an error, or if we
                # started a new game.
                # TODO(benkraft): do this in a less ad-hoc way.
                game.put()
        except engine.Misplay as e:
            answer = {
                'response_type': 'ephemeral',
                "text": str(e),
            }
            logging.info("Misplay: %s" % e)
        except Exception as e:
            answer = {
                'response_type': 'ephemeral',
                "text": "Something went wrong!",
            }
            logging.exception(e)
        self.response.write(json.dumps(answer))


app = webapp2.WSGIApplication([
    ('/', Command),
])
