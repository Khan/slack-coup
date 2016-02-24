import datetime
import json
import random

import webapp2

from google.appengine.ext import ndb


# dict from full name to short code
CARDS = {
    'ambassador': 'amba',
    'assassin': 'assn',
    'captain': 'capt',
    'contessa': 'cont',
    'duke': 'duke',
}


class Card(ndb.Model):
    """StructuredProperty."""
    card = ndb.StringProperty()
    eliminated = ndb.BooleanProperty()

    def view(self, public):
        card = CARDS[self.card].upper()
        if self.eliminated:
            return '~[%s]~' % card
        elif not public:
            return '[%s]' % card
        else:
            return '[????]'


class Player(ndb.Model):
    """StructuredProperty on GameState."""
    username = ndb.StringProperty()
    cards = ndb.StructuredProperty(Card, repeated=True)  # should be exactly 2
    money = ndb.IntegerProperty()

    @property
    def mention(self):
        return '@' + self.username

    def view(self, public):
        cards = ' '.join(card.view(public) for card in self.cards)
        return '%s: %s\u2022 %s' % (self.username, self.money, cards)


class GameState(ndb.Model):
    """Per-game singleton to store the game state.

    Keyed on "team_id#channel_id".
    """
    last_player = ndb.StringProperty(required=False)
    last_action = ndb.StringProperty(required=False)
    last_action_challenger = ndb.StringProperty(required=False)
    last_action_blocker = ndb.StringProperty(required=False)
    last_action_block_challenger = ndb.StringProperty(required=False)
    last_action_timestamp = ndb.DateTimeProperty()
    unused_cards = ndb.StructuredProperty(Card, repeated=True)
    players = ndb.StructuredProperty(Player, repeated=True)

    def get_player(self, username):
        for player in self.players:
            if player.username == username:
                return player
        return None


def deal_cards(existing_game, game_id, players):
    if existing_game:
        return {
            'response_type': 'ephemeral',
            'text': "There's already a game running in this room!  "
                    "To cancel it and start a new one, "
                    "`/coup restart [usernames]`."
        }
    cards = [Card(card=card, eliminated=False)
             for card in CARDS for _ in xrange(3)]
    random.shuffle(cards)
    players = [Player(username=player.lstrip('@'), money=2,
                      cards=[cards.pop(), cards.pop()])
               for player in players]
    game = GameState(
        last_action_timestamp=datetime.datetime.now(),
        unused_cards=cards,
        players=players)
    game.put()
    return {
        'response_type': 'in_channel',
        'text': "%s, get ready for a game of Coup!  Use `/coup cards` to view "
                "your cards, and `/coup action <action>` to take an action.  "
                "%s, it's your turn." % (
                    ' '.join(player.mention for player in players),
                    players[0].mention)
    }


def cancel_game(game):
    game.delete()
    return {
        'response_type': 'in_channel',
        'text': "Game over, everyone loses.  To start a new game, "
                "`/coup deal`.",
    }


def view_status(game, response_type):
    return {
        'response_type': response_type,
        'text': '\n'.join(player.view(public=True) for player in game.players)
    }


def view_self(player):
    return {
        'response_type': 'ephemeral',
        'text': player.view(public=False),
    }


@ndb.transactional
def run_command(game_id, username, args):
    game = GameState.get_by_id(game_id)
    # These don't need an existing game or a player.
    if args[0] in ('deal', 'new'):
        return deal_cards(game, game_id, args[1:])
    elif args[0] == 'restart':
        if game:
            cancel_game(game)
        return deal_cards(None, game_id, args[1:])

    # These need a game, but not a player.
    if not game:
        return {
            'response_type': 'ephemeral',
            'text': "There's no game running in this channel.  To start a new "
                    "game, `/coup deal`.",
        }
    elif args[0] == 'cancel':
        return cancel_game(game)
    elif args[0] in ('view', 'board'):
        return view_status(game, 'ephemeral')
    elif args[0] in ('status', 'state'):
        return view_status(game, 'in_channel')

    # These need a game and a player.
    player = game.get_player(username)
    if not player:
        return {
            'response_type': 'ephemeral',
            'text': "You're not in this game!  To start a new game, "
                    "`/coup deal`."
        }
    elif args[0] in ('cards', 'money', 'me', 'look'):
        return view_self(player)

    return {
        "text": "This command is not implemented yet."
    }


class Command(webapp2.RequestHandler):
    def post(self):
        """Endpoint for the slash command."""
        # TODO(benkraft): check the token to prevent abuse?
        game_id = "%s#%s" % (self.request.POST['team_id'],
                             self.request.POST['channel_id'])
        username = self.request.POST['user_name']
        args = self.request.POST['text'].split()
        answer = run_command(game_id, username, args)
        self.response.write(json.dumps(answer))


app = webapp2.WSGIApplication([
    ('/', Command),
])
