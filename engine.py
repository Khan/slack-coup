import random

from google.appengine.ext import ndb

# dict from full name to short code
CARDS = {

    'ambassador': 'amba',
    'assassin': 'assn',
    'captain': 'capt',
    'contessa': 'cont',
    'duke': 'duke',
}


# dict from alias to canonical name
ACTION_NAMES = {
    'ambassador': 'exchange',
    'ambassade': 'exchange',
    'exchange': 'exchange',
    'assassinate': 'assassinate',
    'assassin': 'assassinate',
    'captain': 'steal',
    'steal': 'steal',
    'take': 'steal',
    'duke': 'tax',
    'tax': 'tax',
    'income': 'income',
    'money': 'income',
    'foreignaid': 'foreignaid',
    'foreign': 'foreignaid',
    'aid': 'foreignaid',
    'coup': 'coup',
}

ACTIONS = set(ACTION_NAMES.itervalues())

ACTION_COSTS = {
    'assassinate': 3,
    'coup': 7,
}

ACTION_GAINS = {
    'steal': 2,
    'tax': 3,
    'income': 1,
    'foreignaid': 2,
}

ACTION_CARDS = {
    'exchange': 'ambassador',
    'assassinate': 'assassin',
    'steal': 'captain',
    'tax': 'duke',
}

ACTION_BLOCKS = {
    'assassinate': {'contessa'},
    'steal': {'ambassador', 'captain'},
    'foreignaid': {'duke'},
}

ACTIONS_WITH_TARGETS = {'assassinate', 'steal', 'coup'}

CARD_LOSS_ACTIONS = {'assassinate', 'coup'}

ACTIONS_WITH_RESPONSE = CARD_LOSS_ACTIONS | {'exchange'}


def _join_messages(msgs):
    return '\n'.join(msg for msg in msgs if msg)


class Misplay(Exception):
    pass


class Card(ndb.Model):
    """StructuredProperty."""
    name = ndb.StringProperty()
    eliminated = ndb.BooleanProperty()

    def view(self, public, strike=True):
        name = CARDS[self.name].upper()
        if self.eliminated and strike:
            return '~[%s]~' % name
        elif not public or self.eliminated:
            return '[%s]' % name
        else:
            return '[????]'


class Player(ndb.Model):
    """StructuredProperty on GameState."""
    username = ndb.StringProperty()
    cards = ndb.StructuredProperty(Card, repeated=True)
    money = ndb.IntegerProperty()

    @property
    def mention(self):
        return '@' + self.username

    def view(self, public):
        if self.is_out():
            cards = ' '.join(card.view(public, False) for card in self.cards)
            return '~%s: %s~' % (self.username, self.money, cards)
        else:
            cards = ' '.join(card.view(public) for card in self.cards)
            return '%s: %s\u2022 %s' % (self.username, self.money, cards)

    def live_cards(self):
        return [card for card in self.cards if not card.eliminated]

    def live_card_names(self):
        return [card.name for card in self.live_cards()]

    def find_live_card(self, card_name):
        for card in self.cards:
            if card_name == card.name and not card.eliminated:
                return card
        return None

    def remove_card(self, card_name):
        for i, card in enumerate(self.cards):
            if card_name == card.name and not card.eliminated:
                del self.cards[i]
                return card
        raise ValueError("No such card")

    def is_out(self):
        return len(self.live_cards()) == 0

    def one_card(self):
        return len(self.live_cards()) == 1

    def __eq__(self, other):
        return isinstance(other, Player) and self.username == other.username


class GameState(ndb.Model):
    """Per-game singleton to store the game state.

    Keyed on "team_id#channel_id".
    """
    last_action = ndb.StringProperty(required=False)
    last_action_target = ndb.StringProperty(required=False)
    # One of:
    # READY
    # ACTED
    # CHALLENGED
    # CHALLENGE_LOST
    # CHALLENGE_LOSS_RESOLVED
    # BLOCKED
    # BLOCK_CHALLENGED
    # BLOCK_CHALLENGE_WON
    # BLOCK_CHALLENGE_LOST
    # BLOCK_CHALLENGE_LOSS_RESOLVED
    # CARDS_TAKEN
    status = ndb.StringProperty()
    challenger = ndb.StringProperty(required=False)
    blocker = ndb.StringProperty(required=False)
    blocked_with = ndb.StringProperty(required=False)
    last_timestamp = ndb.DateTimeProperty(auto_now=True)
    unused_cards = ndb.StructuredProperty(Card, repeated=True)
    # Next player first
    players = ndb.LocalStructuredProperty(Player, repeated=True)

    def remaining_players(self):
        return [player for player in self.players if not player.is_out()]

    def get_player(self, username):
        for player in self.players:
            if player.username == username:
                return player
        return None

    def next_player(self):
        return self.remaining_players()[0]

    def last_player(self):
        return self.remaining_players()[-1]

    def player_usernames(self):
        return [player.username for player in self.players]

    def mention_all(self):
        return ' '.join(player.mention for player in self.players)

    def winner(self):
        remaining_players = self.remaining_players()
        if len(remaining_players) == 1:
            return remaining_players[0].username
        return None

    def status_line(self):
        winner = self.winner()
        action_bit = "%s used %s" % (
            self.last_player().username, self.last_action)
        if winner:
            return "*%s has won!*" % winner
        elif self.status == 'READY':
            return "It's %s's turn." % self.next_player().username
        elif self.status == 'ACTED':
            return "%s." % action_bit
        elif self.status == 'CHALLENGED':
            return "%s, and %s challenged." % (action_bit, self.challenger)
        elif self.status == 'CHALLENGE_LOST':
            return ("%s, and %s's challenge failed.  %s must flip a card." % (
                action_bit, self.challenger, self.challenger))
        elif self.status == 'CHALLENGE_LOSS_RESOLVED':
            return "%s, and %s's challenge failed." % (
                action_bit, self.challenger)
        elif self.status == 'BLOCKED':
            return "%s, and %s blocked with a %s." % (
                action_bit, self.blocker, self.blocked_with)
        elif self.status == 'BLOCK_CHALLENGED':
            return "%s, %s blocked with a %s, and %s challenged." % (
                action_bit, self.blocker, self.blocked_with)
        elif self.status == 'BLOCK_CHALLENGE_WON':
            return ("%s, %s blocked with a %s, and %s's challenge was "
                    "successful." % (action_bit, self.blocker,
                                     self.blocked_with, self.challenger))
        elif self.status == 'BLOCK_CHALLENGE_LOST':
            return ("%s, %s blocked with a %s, and %s's challenge failed.  "
                    "%s must flip a card." % (
                        action_bit, self.blocker, self.blocked_with,
                        self.challenger, self.challenger))
        elif self.status == 'BLOCK_CHALLENGE_LOSS_RESOLVED':
            return "%s, %s blocked with a %s, and %s's challenge failed." % (
                action_bit, self.blocker, self.blocked_with, self.challenger)
        elif self.status == 'CARDS_TAKEN':
            return "%s, and has taken cards." % action_bit
        else:
            raise ValueError("Unknown status %s" % self.status)

    def status_view(self):
        lines = [self.status_line()]
        for player in self.players:
            lines.append(player.view(public=True))
        return _join_messages(lines)

    # After calling any of the following, you must then put() self.
    @staticmethod
    def create(players):
        cards = [Card(name=name, eliminated=False)
                 for name in CARDS for _ in xrange(3)]
        random.shuffle(cards)
        players = [Player(username=player.lstrip('@'), money=2,
                          cards=[cards.pop(), cards.pop()])
                   for player in players]
        return GameState(status='READY', unused_cards=cards, players=players)

    # ACTIONS

    def take_action(self, player, action, target):
        if player != self.next_player():
            raise Misplay("It's not your turn!  It's %s's turn." %
                          self.next_player().username)
        elif not (self.status == 'READY'
                  or self.status in ('ACTED', 'BLOCKED',
                                     'CHALLENGE_LOSS_RESOLVED')
                  and self.last_action not in ACTIONS_WITH_RESPONSE):
            # TODO(benkraft): say what we're waiting on
            raise Misplay("It's not time for the next person to go yet!")
        elif action not in ACTION_NAMES:
            raise Misplay("I've never heard of that action, try one of these: "
                          "%s." % ' '.join(ACTIONS))
        action = ACTION_NAMES[action]
        cost = ACTION_COSTS.get(action, 0)
        if player.money < cost:
            raise Misplay("You don't have enough money to do that; you need "
                          "%s and only have %s." % (cost, player.money))
        elif player.money >= 10 and action != 'coup':
            raise Misplay("You have 10 coins; you must coup.")
        elif action in ACTIONS_WITH_TARGETS:
            if not target:
                raise Misplay("That action needs a target.")
            if target.is_out():
                raise Misplay("%s is out.")

        # Okay, we're ready to act.  Finish up the last action.
        responses = []
        responses.append(self._flush_action())
        responses.append(self._begin_action(action, target))
        responses.append(self._maybe_autoresolve_action())
        return _join_messages(responses)

    def _flush_action(self):
        """Cannot be used for ACTIONS_WITH_RESPONSE."""
        if not self.last_action:
            # If the last action has been flushed, this is a no-op.
            return
        if self.last_action in ACTION_GAINS:
            self.last_player().money += ACTION_GAINS[self.last_action]
        if self.last_action == 'steal':
            self.get_player(self.last_action_target).money -= 2
        text = "%s's %s was completed successfully." % (
            self.last_player().username, self.last_action)
        self._clear_action()
        return text

    def _clear_action(self):
        self.last_action = None
        self.last_action_target = None
        self.challenge_loser = None
        self.blocker = None
        self.blocked_with = None
        self.status = 'READY'

    def _begin_action(self, action, target):
        self.last_action = action
        self.last_action_target = target.username if target else None
        self.status = 'ACTED'
        # Costs get deducted immediately, since they happen no matter what;
        # gains get processed when the action succeeds.
        if action in ACTION_COSTS:
            self.next_player().money -= ACTION_COSTS[action]
        # Advance the turn
        self.players = self.players[1:] + [self.players[0]]
        while self.players[0].is_out():
            self.players = self.players[1:] + [self.players[0]]

        if target:
            target_text = " on %s" % target.username
        else:
            target_text = ""
        responses = ["%s used %s%s!" % (self.last_player().username, action,
                                        target_text)]
        if action in ACTION_CARDS:
            responses.append("If you wish to challenge, `/coup challenge`.")
        if action in ACTION_BLOCKS:
            responses.append("If you wish to block, "
                             "`/coup block <with_card>`.")
        return _join_messages(responses)

    def _maybe_autoresolve_action(self, challenge_complete=False,
                                  block_complete=False):
        if self.last_action == 'income':
            # Don't bother saying it completed, that's obvious.
            self._flush_action()
            return
        elif self.last_action == 'coup':
            target = self.get_player(self.last_action_target)
            if target.one_card():
                return self._flip_card(target, target.live_cards()[0])
        if self.last_action in CARD_LOSS_ACTIONS:
            return "If you're ready to lose a card, `/coup lose <card>`."
        elif self.last_action == 'exchange':
            return "To pick up your cards, `/coup exchange`."
        elif (block_complete
              or challenge_complete and self.last_action not in ACTION_BLOCKS):
            return self._flush_action()

    # FLIPPING CARDS

    def _flip_card(self, player, card):
        card.eliminated = True
        # If this eliminated a player, and it was their turn, advance the turn.
        while self.players[0].is_out():
            self.players = self.players[1:] + [self.players[0]]
        text = "%s flipped over a %s." % (player.username, card.name)
        winner = self.winner()
        if winner:
            return _join_messages([text, "%s wins!" % winner])
        else:
            return text

    def _redeal_card(self, player, card_name):
        c = player.remove_card(card_name)
        self.unused_cards.append(c)
        random.shuffle(self.unused_cards)
        player.cards.append(self.unused_cards.pop())
        return "%s drew a new card." % player.username

    # CHALLENGES

    def pose_challenge(self, challenger):
        # TODO(benkraft): make them say what to challenge, to prevent races?
        # TODO(benkraft): don't let you challenge yourself
        if self.status == 'ACTED' and self.last_action in ACTION_CARDS:
            self.status = 'CHALLENGED'
            verb = self.last_action
        elif self.status == 'BLOCKED':
            self.status = 'BLOCK_CHALLENGED'
            verb = 'block'
        else:
            raise Misplay("There's nothing to challenge.")
        self.challenger = challenger.username
        challengee = self._challengee()

        text = "%s has challenged %s's %s" % (
            challenger.username, challengee.username, verb)
        if challengee.one_card():
            return _join_messages([text, self._resolve_challenge(
                self, challengee.live_cards()[0])])
        else:
            return _join_messages(
                [text, "%s, please flip a card with `/coup show <card>`."
                 % challengee.username])

    def resolve_challenge(self, player, card_name):
        challengee = self._challengee()
        if (challengee != player
                or self.status not in ('CHALLENGED', 'BLOCK_CHALLENGED')):
            raise Misplay("You haven't been challenged.")
        card = challengee.find_live_card(card_name)
        if not card:
            raise Misplay("You don't have that card.")

        return self._resolve_challenge(card)

    def lose_challenge(self, player, card_name):
        challenger = self.get_player(self.challenger)
        card = challenger.find_live_card(card_name)
        if player != challenger:
            raise Misplay("You haven't been challenged.")
        elif self.status not in ('CHALLENGE_LOST',
                               'BLOCK_CHALLENGE_LOST'):
            raise Misplay("You haven't been challenged.")
        elif not card:
            raise Misplay("You don't have that card.")

        text = self._flip_card(challenger, card)
        if self.status == 'CHALLENGE_LOST':
            self.status = 'CHALLENGE_LOSS_RESOLVED'
            if self.last_action in ACTION_BLOCKS:
                return _join_messages([text, "If you wish to block, "
                                       "`/coup block <with_card>`."])
            else:
                return _join_messages(
                    [text, self._maybe_autoresolve_action(
                        challenge_complete=True)])
        else:  # self.status == 'BLOCK_CHALLENGE_LOST'
            self.status = 'BLOCK_CHALLENGE_LOSS_RESOLVED'
            failed_text = "The %s was blocked." % self.last_action
            self._clear_action()
            return _join_messages([text, failed_text])

    def _challengee(self):
        if self.status == 'CHALLENGED':
            return self.players[-1]
        else:
            return self.get_player(self.blocker)

    def _resolve_challenge(self, card):
        challengee = self._challengee()
        challenger = self.get_player(self.challenger)
        text = "%s flipped over a %s." % (challengee.username, card.name)
        flip_card_text = ("%s, please flip a card with `/coup flip <card>`."
                          % challenger.username)
        # TODO(benkraft): refactor to deduplicate?
        if self.status == 'CHALLENGED':
            if card.name == ACTION_CARDS[self.last_action]:
                self.status = 'CHALLENGE_LOST'
                redeal_text = self._redeal_card(challengee, card.name)
                if challenger.one_card():
                    return _join_messages(
                        [text, redeal_text, self.lose_challenge(
                            challenger, challenger.live_cards()[0])])
                else:
                    return _join_messages([text, redeal_text, flip_card_text])
            else:
                failed_text = "The %s failed." % self.last_action
                self._clear_action()
                return _join_messages([text, failed_text])
        else:  # self.status == 'BLOCK_CHALLENGED'
            if card.name == self.blocked_with:
                self.status = 'BLOCK_CHALLENGE_LOST'
                redeal_text = self._redeal_card(challengee, card)
                if challenger.one_card():
                    return _join_messages(
                        [text, redeal_text, self.lose_challenge(
                            challenger, challenger.live_cards()[0])])
                else:
                    return _join_messages([text, redeal_text, flip_card_text])
            else:
                self.status = 'BLOCK_CHALLENGE_WON'
                return _join_messages([
                    text, "The block failed.",
                    self._maybe_autoresolve_action(block_complete=True)])

    # BLOCKS

    def pose_block(self, blocker, card_name):
        # TODO(benkraft): guess card if it's unique
        if self.status not in ('ACTED', 'CHALLENGE_LOSS_RESOLVED'):
            raise Misplay("You can't block right now.")
        elif self.last_action not in ACTION_BLOCKS:
            raise Misplay("%s can't be blocked." % self.last_action)
        elif self.last_player() == blocker:
            raise Misplay("You can't block yourself.")
        # Foreign aid can be blocked by anyone; steal and assassinate can only
        # be blocked by their targets.
        elif (self.last_action != 'foreignaid'
              and self.last_action_target != blocker.username):
            raise Misplay("Only the target of a %s can block it."
                          % self.last_action)
        elif card_name not in ACTION_BLOCKS[self.last_action]:
            raise Misplay("You can't block %s with a %s."
                          % (self.last_action, card_name))

        self.status = 'BLOCKED'
        self.blocker = blocker.username
        self.blocked_with = card_name
        return "%s has blocked %s's %s with a %s" % (
            blocker.username, self.last_player().username,
            self.last_action, card_name)

    # AMBASSADOR

    def take_cards(self, player):
        if player != self.last_player():
            raise Misplay("It's not your turn.")
        elif self.last_action != 'exchange':
            raise Misplay("You didn't exchange.")
        elif self.status not in ('ACTED', 'CHALLENGE_LOSS_RESOLVED',
                                 'BLOCK_CHALLENGE_LOSS_RESOLVED'):
            # TODO(benkraft): say why
            raise Misplay("You can't take your cards right now.")
        self.status = 'CARDS_TAKEN'
        random.shuffle(self.unused_cards)
        card1 = self.unused_cards.pop()
        card2 = self.unused_cards.pop()
        player.cards.extend([card1, card2])
        return ("You got a %s and a %s.  To choose which cards to keep, "
                "`/coup keep <card1> <card2>`." % (card1.name, card2.name))

    def keep_cards(self, player, card1_name, card2_name):
        if player != self.last_player():
            raise Misplay("It's not your turn.")
        elif self.last_action != 'exchange':
            raise Misplay("You didn't exchange.")
        elif self.status != 'CARDS_TAKEN':
            raise Misplay("You didn't take cards!  "
                          "To take cards, `/coup take`.")
        elif (card1_name == card2_name
              and not player.live_card_names().count(card1_name) >= 2):
            raise Misplay("You don't have two %ss." % card1_name)
        for card in [card1_name, card2_name]:
            if not player.find_live_card(card):
                raise Misplay("You don't have a %s." % card)
        for card in [card1_name, card2_name]:
            player.remove_card(card)
        self._clear_action()
        return "%s returned their cards." % player.username

    # CARD LOSS

    def lose_card(self, player, card_name):
        if self.last_action not in CARD_LOSS_ACTIONS:
            raise Misplay("You don't need to lose a card now.")
        elif player.username != self.last_action_target:
            raise Misplay("You weren't the target of the %s."
                          % self.last_action)
        elif self.status not in ('ACTED', 'CHALLENGE_LOSS_RESOLVED',
                                 'BLOCK_CHALLENGE_LOSS_RESOLVED'):
            raise Misplay("It's not time to flip a card yet.")
        card = player.find_live_card(card_name)
        if not card:
            raise Misplay("You don't have a %s." % card_name)
        text = self._flip_card(player, card)
        self._clear_action()
        return text
