#!/usr/local/bin/python3.6

# ##################################################
# Compute Velocity -- Stop Starting, Start Finishing
# ##################################################
#
# This example shows a functional approach to defining processing rules.
# We'll look at an application that does various kinds analytical
# processing steps in a functional style. 
# This includes Extract, Transform, Filter, Classify, Reduce, and Report. 
#
# In particular, we'll define each of the complex classification rules as a small
# function. Doing this lets us use higher-order functions like
# ``map()``, ``filter()``, and variations on ``reduce()`` 
# to perform the overall tasks.
#
# The practical result is counts of Trello cards started, deleted,
# and finished, grouped by date. This allows simple computations of
# velocity starting and velocity finishing.

# ..  contents::

# Module Docstring
# ================

# ::

"""
Count Actions on a Trello Board.

Given a board name, count actions to get a raw "create" and "finish" count.

This involves several kinds of functional-programming mappings.

-   From trello document to an internal Action namedtuple.

    This uses a collection of individual functions (some expressed as lambdas)
    to build each attribute of the ``Action`` object.

-   Some lists are filtered to exclude contents of the list.

    This uses a collection of individual functions to determine which lists
    to pass and which to reject. The idea is that a simple list of functions
    can provide the "pass" rules.
    
-   A collection of rules is used to map the Action to an Event summary.

    The "create" event comes from copyCard, createCard, moveCardToBoard, 
        and convertToCardFromCheckItem actions.
    
    The "remove" event is deleteCard and moveCardFromBoard.

    The "finish" count depends on moving cards to a specific list or closing
        cards. This means identifying all of the "finished" lists.
        
    This is done through a list of decision rules. 
    
-   The event summaries for each date are counted.
    
A number of final transformations are performed to modify the raw counts
into a table with date as the row key and the event types spread across the columns.
This tabular pivot is helpful for graphing and subsequent decision support.
"""

# Trello Data Access
# ==================

# The raw data comes from Trello. Visit http:://trello.com for details.
#
# We're using the Trello API accessed via py-trello.
# See https://github.com/sarumont/py-trello/tree/master/trello 
# And https://pypi.python.org/pypi/py-trello/0.9.0.
#
# Generally, we're interested in all events for a given board.
# Therefore, the ``Board`` class definition is what we'll focus on.
#
# Boards have actions. They also have lists.
# 
# Often, lists have distinct semantics. We recognize three kinds of lists.
#
# -  Reference data or Ungroomed Backlog. 
#    The cards in these lists are neither stories nor tasks.
#    The lists should simply be ignored for computing velocity.
# 
# -  Finish States. The cards in these lists represent completed tasks or
#    stories. This gives the "finishing" rate.
#
# -  Other states. The cards in these lists are in-process stories or tasks.
#    This gives the "starting" rate. 
#
# The point, after all this analysis, is to stop starting and start finishing.

# Imports
# ========

# Here are the other modules we'll need.

from collections import Counter, namedtuple, defaultdict
import csv
import datetime
from enum import Enum
import itertools
from pathlib import Path
from pprint import pprint
import re
import sys

# We'll use some type hints to get to a successfully strict
# set of hints.

from typing import (
    List, Dict, Tuple,
    Iterator, Iterable, Callable, Union, NewType, Any,
    TypeVar,
    Callable,
    DefaultDict,
    NamedTuple,
    cast,
)

# The Trello libraries. These lack hints.

from trello import TrelloClient  # type: ignore [import]
from trello.board import Board  # type: ignore [import]


# Here are a few functions to help with functional programming.
#
# A function we can use to pluck the first
# item from an iterable. This seems better than using 
# ``itertools.take(1, iterable)``

T_ = TypeVar("T_")

first: Callable[[Iterator[T_]], T_] = lambda iterable: next(iterable)

# Another function to slightly simplify filtering data.

non_none: Callable[[Iterable[T_]], Iterator[T_]] = lambda iterable: filter(None, iterable)

# Parse a Configuration File
# ==========================

# This is an overhead for extracting a configuration from a
# small shell-friendly settings file. 
# 
# The file contains lines that are -- precisely -- shell environment
# variable settings. Here's what the ``keys.sh`` file looks like.
#
# ..  code:: bash
#
#     export TRELLO_API_KEY=...
#     export TRELLO_API_SECRET=...
#     export OAUTH_TOKEN=...
#     export OAUTH_TOKEN_SECRET=...
#     export board_name=Blog: Algorithmic study
#     export reject=Reference Material
#     export finished=Things Actually Finished
#
# Why use a format like this?
# 
# It follows in a simple way from the onboarding process
# described in the README.rst. 
#
# In order to get the OATH token and secret, we must run the following command:
#
# ..  code:: bash
#
#     $ python3 -m trello.util
#
# This command requires the ``TRELLO_API_KEY`` and ``TRELLO_API_SECRET``
# as environment variables. We could set the manually, but
# a more reliable way to do this is to put the first values into a file named 
# ``keys.sh`` and then use ``source ./keys.sh`` to set the environment variables.
#
# Since we have to start that way, we might as well continue that way.
# All of the configuration parameters look like environment variables settings.

def get_config(config_text: str) -> Dict[str, str]:
    """
    Get the configuration file value from text.

    This handles the ``export`` keyword gracefully.
        
    :param config_path: a Path object to identify the configuration file
    :returns: dictionary with configuration settings.
    """
    line_pat = re.compile(r'(?:export\s+)?(\w+)=(.*)')
    matches = map(line_pat.match, config_text.splitlines())
    config = {
        m.group(1): m.group(2) for m in matches if m
    }
    return config
    
# Here's an example of how this works
#
# ..  code:: python
#
#     >>> from action_counts import *
#     >>> get_config("export A=B")
#     {'A': 'B'}
#     >>> get_config("C=D\nE=F")
#     {'C': 'D', 'E': 'F'}
#
    
# Trello Exploration
# ==================

# These first two functions aren't essential. They're here to 
# support exploration of a Trello account and board to locate
# the proper names for lists.
#
# Get a list of all boards accessible with the given credentials.

def board_list(client: TrelloClient) -> None:
    """
    Given the client, print all boards.
    
    :param client: The connected TrelloClient instance.
    """
    for b in client.list_boards():
        print(b.name)

# Get a list of all lists on a given board.

def list_list(client: TrelloClient, board_name: str) -> None:
    """
    Given a client and a board name, print all lists on that board.

    :param client: The connected TrelloClient instance
    :param board_name: A name for a board
    """
    for board in find_board(client, board_name):
        print(board.name)
        for list_ in board.all_lists():
            print(list_.name)

# The ``find_board()`` function locates all of the relevant boards that match
# a given name. Often, we'll simply take the first matching
# board. But, we could process all similar boards.

def find_board(client: TrelloClient, name: str) -> Iterator[Board]:
    """
    Find boards with names starting with the given name string.
    
    :param client: The connected TrelloClient instance
    :param name: A name for a board
    :returns: Yields all matching Board instances
    """
    for b in client.list_boards():
        if b.name.startswith(name):
            yield b

# Action Objects
# ==============
#
# Our processing is focused on analyzing ``Action`` instances.
# 
# This contains the attributes we care about from a Trello action
# document.
# 
# - date -- essential for computing velocities.
# - action name -- these will be mapped to event summaries.
# - list name -- these help fine-tune the event mapping.
# - card name -- this can be helpful for debugging.
#
# We also include the original ("raw") action document as an aid for
# debugging.

class Action(NamedTuple):
    date: datetime.date
    action: str
    card: str
    list: str
    raw: dict[str, Any]

# We've made them namedtuples because they're immutable. They expose
# certain data attributes. 
# This is not stateful data.
# It's a historical record. For this kind of analysis, a simple ``map()``
# to transform source documents to ``Action`` instances seems like the ideal
# solution.
#
# There are two parts to building the sequence of ``Action`` instances.
#
# - `Action Transformations`_ these are field-by-field transformations.
#
# - `Action Builder`_ this combines the fields to create the resulting object.
#
# Action Transformations
# -----------------------
#
# These functions (or lambdas) create the individual fields
# of the ``Action`` instance.
#
# There are four customized fields:
#
# - **date**. This parses the UTC time.
#   Rather than define a mapping for the "Z" timezone, we force in UTC
#   to create a timezone-aware ``datetime`` object. We can then extract
#   a local date.

UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
make_action_date: Callable[[dict[str, str]], datetime.date] = (lambda document:
    datetime.datetime
    .strptime(document['date'], UTC_FORMAT)
    .replace(tzinfo=datetime.timezone.utc)
    .date()
    )
    
# - **action**. A copy of a field without any transformation.

make_action_action: Callable[[dict[str, str]], str] = lambda document: document['type']

# - **card**.  The name or the ID of a card. Not all cards have names. 
#   This is confusing as a lambda. So it's defined as a function.

def make_action_card(document : dict[str, dict[str, dict[str, str]]]) -> str:
    if 'name' in document['data']['card']:
        # Creates/Moves
        return document['data']['card']['name']
    else:
        # Deletes
        return document['data']['card']['id']

# - **list**. The name of a list. There are two places to 
#   look in the action document. 
#
#   Since the entire document is available, we could use ``document['type']`` 
#   to distinguish the two cases. It's simpler, however, to simply look in
#   all of the usual places for the information, since there are only two choices.
#
#   It's unclear what other actions we need to process; we'll consider the others
#   as uniformly ``False``.

def make_action_list(document : dict[str, dict[str, dict[str, str]]]) -> str:
    if 'list' in document['data']:
        # Creates/Deletes
        return document['data']['list']['name']
    elif 'listAfter' in document['data']:
        # Moves
        return document['data']['listAfter']['name']
    else:
        # Perhaps we should raise an exception?
        return ""
        
# We'll use all of these field-level transformation functions to generate
# the required ``Action`` instance. 
#
# Action Builder
# --------------
#
# We need to build complete ``Action`` instances by applying the field-level
# transformations. Each transformation is independent, and extracts one field's
# value from the source document.
#
# There are cases where a field might be decomposed. This would lead to
# two-tier processing. A single lambda would create a tuple with the values.
# Other lambdas would chose items from the tuple. With a simple cache, this
# can be very fast and still functionally focused with no stateful processing. 
#
# First, we have a field-to-function mapping. Each target field name
# from the ``Action`` namedtuple is paired with a function that
# builds that field from the source document.

ACTION_FIELD_MAP: dict[str, Callable[..., Any]] = {
    'date': make_action_date,
    'action': make_action_action,
    'card': make_action_card,
    'list': make_action_list,
    'raw': lambda document: document
}

# Ideally, we'd derived the definition of the ``Action`` class from this mapping.
# Doing that gets the presentation a little out of order.
# We aren't strictly DRY about this. A change to this mapping
# will require a change to the namedtuple function above.

# Given this set of fields, we can then apply each
# function to the source document and build an Action instance.

# This is sometimes implemented as a static method of the ``Action`` class.
# It's also sometimes implemented as a ``__post_init__()`` method of a dataclass.

def make_action(raw_action : dict[str, Any]) -> Action:
    return Action(
        **{field: transform(raw_action) for field, transform in ACTION_FIELD_MAP.items()}
    )

# Let's examine this closely.
#
# 1. The ACTION_FIELD_MAP has field names and transform functions.
#
# 2. We apply the transform function to the raw_action document.
#
# 3. The result is a dictionary that has the structure required by the ``Action`` namedtuple.
#
# 4. We transform this into an ``Action`` instance.
#
# The point behind this function is to apply it to a board to
# emit ``Action`` documents for analysis.

def action_iter(board: Board, actions: list[str], limit: int = 100) -> Iterator[Action]:
    """
    Iterate over all matching actions on this board.

    This projects raw document into simplified
    :class:`Action` instances. 
    
    :returns: Action namedtuple instances.
    """
    return map(make_action, board.fetch_actions(actions, action_limit=limit))
    
# This, too, coud be reframed into two simpler parts.
#
# -  ``query = board.fetch_actions(actions, action_limit=limit)``
#
# -  ``results = lambda query: map(make_action, query)``
#
# It seems slightly nicer to leave them combined into a single function.
# The goal is to be able to do this:
#  
# ..  code:: python
#
#     for action in action_iter(Board, ['createCard', ...]):
#         summarize the ``Action`` instance.
#
# We provide a Trello ``Board`` instance and a list of actions to query.
# This
#
# Action Input Wrap-up
# --------------------
# 
# Almost all raw-data processing has this same design pattern.
#
# 1. Define the transformations from source to useful data.
#
# 2. Define a ``make_X()`` function to apply the transformations and create the
#    useful instances.
#
# 3. Apply the ``make_X()`` function to the source documents.
#
# The result is an iterator over the mapping from source to useful ``Action``
# instance. 
#
# There is no stateful data. Everything is defined independently. The fields
# can evolve independently; new features can be added and bugs fixed without
# any "ripple effect".
# 
# The next step is to summarize the ``Action`` instances.
#
# Event Summaries
# ================
#
# We categorize ``Actions`` into higher-level groups. 
# Here's an enumeration of the different kinds of Events we're going to count.

Event = Enum('Event', ['ignore', 'create', 'remove', 'finish'])

# The events have the following semantics.
#
# - ignore. These actions are irrelevant to our analysis. 
# 
# - create. These actions created on card on a non-reference list. 
#   This measures our "starting" velocity.
#
# - remove. These actions removed cards, decreasing the interesting
#   create events. This reduces the "starting" velocity.
#
# - finish. These actions finished at story. This is the "finishing" velocity.
# 
# We can use this to determine if we're starting too many things and finishing
# too few things. We can help re-oriented a team to stop starting and start finishing.
#
# Action Names
# ------------
#
# As an obscure detail, we have two slightly different representations
# for the raw action names that are defined by Trello.
#
# - The action text as seen in the document.
#
# - A variation on the action text as used to query the actions from a Board.
#
# The action type might be ``"updateCard"``. The query might be ``"updateCard:closed"``.
#
# We'll parse the action from the query-sting version of an action type.

parse_action: Callable[[str], str] = lambda type_text: type_text.partition(':')[0]

#
# ..  code:: python
# 
#     >>> from action_counts import *
#     >>> parse_action('updateCard:closed') 
#     'updateCard'
#
#
# Event Classifiers
# -----------------
#
# The objective is to classify ``Action`` details into ``Event`` categories.
#
# Therefore, we must "classify" or "match" a number of similar ``Action`` instances.
# A rule will map similar instances to a single kind of ``Event``.
#
# The classification is clearly a function of the input ``Action``.
#
# Less clearly, a classification is also a function of configuration details. We'd 
# like to avoid encoding Trello action strings into the rules if we can.
# More fundamentally, we cannot encode the list names into the rules.
# The list names must be run-time, dynamic values.
#
# Further -- to make an attempt at being DRY -- we have two uses for the
# Trello action strings.
# 
# - Transformation Action to Event class.
#
# - Querying Trello for the Actions on a board.
#
# These considerations (configuration and DRY) lead us to use 
# partial functions to define the rule. We can distinguish
# between arguments used to configure the rule and arguments
# that are applied as part of the final decision-making by the rule.
# And we can extract the action strings from the rules to use for querying.
#
# The rules are defined like this:
#
# ..  code:: python
#
#     [(MATCH_RULE, (args, ...), event), ... ]
# 
# We provide a triple with the function, the configuration arguments,
# and the resulting event.
#
# The partial functions are used like this:
#
# ..  code:: python
#
#     MATCH_RULE(*args)(action)
#
# The first wave of argument processing, using ``MATCH_RULE(*args)``, creates a function that 
# makes the final match decision. 
# This first-wave function is subsequently applied to the ``action`` argument 
# for filtering or mapping to an event type.
#

# Some of the rule types require the run-time input of the specific
# lists which count as finished. We do this last-minute binding in a function
# that emits a list of rules, some of which have the list names injected into them.

Match_Args = Union[Tuple[str], Tuple[str, List[str]]]
Filter_Action = Callable[[Action], bool]
Match_Rule = Union[
    Callable[[str], Filter_Action],
    Callable[[str, List[str]], Filter_Action],
]

# While this would be pleasant, it doesn't work:
#     ``Match_Rule = Callable[[*Match_Args], Filter_Action]``

Classifier_Rule_List = List[Tuple[Match_Rule, Match_Args, Event]]

# This was once part of the code, but appears not used... ``Match_Action = Callable[[Action], Event]``.

# There are several rule types:

# - Matches if the text of the action type matches the ``Action.action`` field.

MATCH_ACTION_TYPE: Match_Rule = lambda type_text: lambda action: action.action == type_text

# - Matches if the ``Action.list`` field is in the target lists.

MATCH_IN_LIST: Match_Rule = lambda list_names: lambda action: action.list in list_names

# - Matches if the ``Action.list`` field is not in the target lists.

MATCH_NOT_LIST: Match_Rule = lambda list_names: lambda action: action.list not in list_names
    
# - Matches if the ``Action.action`` text and the ``Action.list`` is in the target lists.

MATCH_ACTION_TYPE_IN_LIST: Match_Rule = (lambda type_text, list_names:
    lambda action: action.action == parse_action(type_text) and action.list in list_names
    )
    
# - Matches if the ``Action.action`` text and the ``Action.list`` is not in the target lists.

MATCH_ACTION_TYPE_NOT_LIST: Match_Rule = (lambda type_text, list_names:
    lambda action: action.action == parse_action(type_text) and action.list not in list_names
    )

def build_action_event_rules(finished_lists: list[str]) -> Classifier_Rule_List:
    """
    Build the Action->Event mapping rules. This requires injecting
    the finished list into the rules.
    
    :param finished_lists: The names of lists that indicate done-ness
    :returns: sequence of three-tuples with rule function, configuration args, and final event.
    """
    return [
        (MATCH_ACTION_TYPE, ('copyCard',), Event.create),
        (MATCH_ACTION_TYPE, ('createCard',), Event.create),
        (MATCH_ACTION_TYPE, ('moveCardToBoard',), Event.create),
        (MATCH_ACTION_TYPE, ('convertToCardFromCheckItem',), Event.create),
    
        (MATCH_ACTION_TYPE, ('deleteCard',), Event.remove),
        (MATCH_ACTION_TYPE, ('moveCardFromBoard',), Event.remove),
    
        (MATCH_ACTION_TYPE_IN_LIST, ('updateCard:closed', finished_lists), Event.finish),
        (MATCH_ACTION_TYPE_IN_LIST, ('updateCard:idList', finished_lists), Event.finish),
        
        (MATCH_ACTION_TYPE_NOT_LIST, ('updateCard:idList', finished_lists), Event.ignore),
    ]

# Each rule is focused on a single kind of input action. This leads to a number
# of rules of a common form. The rules are independent, and we can, add, change, or 
# delete freely.
#
# An alternative design would focus the rules on the output event type.
# We might have a mapping from event type to a list of conditions that indicate the
# defined event. This is a kind of kind of conjunctive normal form.
#
# We might say ``Event.create if any(RULE(action) for rule in create_rules) else None``.
#
# This is a simple optimization. It doesn't have any material performance impact.
# And it combines details into a larger structure, imposing some minor dependencies.
# Also, it makes it difficult to get a simple list of actions to support a Trello
# action query. 
#
# Here's how a collection of rules works.
#
# ..  code:: python
#
#     >>> from action_counts import *
#     >>> finished_lists = ['Some List']
#     >>> EVENT_RULES = build_action_event_rules(finished_lists)
#     >>> action = Action('date', 'copyCard', 'card', 'Some List', None)
#     >>> list(filter(None, (rule_type(*args)(action) and event for rule_type, args, event in EVENT_RULES)))
#     [<Event.create: 2>]
#     >>> action = Action('date', 'updateCard', 'card', 'Some List', None)
#     >>> list(filter(None, (rule_type(*args)(action) and event for rule_type, args, event in EVENT_RULES)))
#     [<Event.finish: 4>, <Event.finish: 4>]
#
# Given an ``Action`` instance, all of the rules in ``EVENT_RULES`` are applied.
# First, they're applied to the fixed configuration arguments to create a decision function.
# Then the resulting decision function is applied to the ``Action`` instance. 
# 
# If the match result is ``True``, we can use ``and event`` to return the ``Event`` type.
#
# If the match result is ``False``, that's the overall result. 
#
# Using ``filter(None, iterable)`` discards all "falsy" values, leaving the ``Event`` type.
# 
# Generally, there's only one match. In some cases, there is more than one because
# our rule doesn't distinguish between moving and closing a card.
#
# Note that each rule is completely independent of all other rules. A change
# to one does not break another. There's no ripple effect. There are no
# stateful variables.
#
# Action Filter
# -------------
#
# We also need to exclude certain lists from analysis. This is a filter that's
# applied early in the process to limit the number of ``Action`` instances that
# are considered.
#
# We can think about this as rejecting certain lists.
# Or we can think about passing all lists which are not those reject lists.
#
# We'll use type hints similar to the Match_Rule hints. These are somewhat
# simpler in that we don't have a query string, merely a list of list names.
#
# So far, there's only one rule. The generalization of this one rule
# seems like quite a bit of overhead. It allows flexibility, and it
# reveals some paralellisms between filtering and transforming ``Action`` instances.

Pass_Args = Tuple[List[str]]
Pass_Rule = Callable[[List[str]], Filter_Action]

Pass_Rule_List = List[Tuple[Pass_Rule, Pass_Args]]

def build_pass_rules(reject_lists: list[str]) -> Pass_Rule_List:
    """
    Build the Action rejection rules. This requires injecting
    the reject list into each rule to create a partial function.
    The function can then be applied to the ``Action``.
    
    The idea is that **all** rules must return True to process the row
    further. Any False is rejection.
    
    :param reject_lists: The names of lists to ignore
    :returns: sequence of two-tuples with rule function, configuration args.
    """
    return [
        (cast(Pass_Rule, MATCH_NOT_LIST), (reject_lists,)),
    ]

# We might have several criteria required for passing.
#
# Currently, there's only a single rule. Since we've defined this as a list,
# we can add rules easily.
#
# ..  code:: python
# 
#     >>> from action_counts import *
#     >>> reject_lists = ['Reject This List']
#     >>> PASS_RULES = build_pass_rules(reject_lists)
#     >>> action1 = Action('date', 'action', 'card', 'Reject This List', None)
#     >>> all(rule_type(*args)(action1) for rule_type, args in PASS_RULES)
#     False
#     >>> action2 = Action('date', 'action', 'card', 'Another List', None)
#     >>> all(rule_type(*args)(action2) for rule_type, args in PASS_RULES)
#     True
#
#     >>> raw_actions = [action1, action2]
#     >>> reject = lambda action: all(rule_type(*args)(action) for rule_type, args in PASS_RULES)
#     >>> passed_actions = filter(reject, raw_actions)
#     >>> list(passed_actions)
#     [Action(date='date', action='action', card='card', list='Another List', raw=None)]
#
# Action to Event Mapping
# -----------------------
#
# The objective is to summarize ``Action`` details into ``Event`` categories.
# We've combined the filter and the categorization into a single function.
# The function is effectively this:
#
#   ``map(classifier, filter(reject, action_iter))``
# 
# This will iterate over a source ``Action`` instances.
# It will pass only those actions not on a reject list.
# It will map all of the classifier rules to each action and pick the first non-false result.

Date = NewType('Date', datetime.date)

def action_event_iter(pass_rules: Pass_Rule_List, 
                      classifier_rules: Classifier_Rule_List, 
                      action_iter: Iterator[Action]) -> Iterator[Tuple[Date, Event, Action]]:
    """
    Classify actions into event type categories.
    
    :param pass_rules: Rules required to pass an action forward for processing
    :param action_event_rules: Rules that identify an event summary for an action
    :param action_iter: An iterator over the source actions.
    :returns: Iterator over (date, event type, action) triples.
    """    
    # Remove the cards on any of the reject lists.
    rule_partials = (rule_type(*args) for rule_type, args in pass_rules)
    pass_filter: Callable[[Action], bool] = lambda action: all(rule(action) for rule in rule_partials)
            
    # Create a list of (date, event) pairs for each rule that matches.
    # Ideally, there's exactly one item in the list, and we take that one item.
    # Since 0 or many matches are problems, a variation on :func:`first` might be appropriate.
    classify = (lambda action: 
        first(
            filter(None, 
                ((action.date, event_classifier, action) if rule_type(*args)(action) else None
                    for rule_type, args, event_classifier in classifier_rules)
            )
        )
    )
    return map(classify, filter(pass_filter, action_iter))

# The combining of filter and map represents an optimization that might be a bad idea.
# Each operation is independent.
# It seems, however, that there's some value in combining the two operations
# because they're both essential to the event classification process.
#
# Action-to-Event Wrap-Up
# -----------------------
#
# The event classification has a universal design pattern.
#
# - Pass Meaningful Events. Our filter used a list of rules. All rules
#   must be true for the ``Action`` to be considered.
# 
# - Apply classifier rules to map an Action to an Event class.
#   In this case, we rejected all falsy outputs (None and False, generally).
#   What remains is zero, one, or many Event types matching the classifier rules.
#   We use ``first`` as a kind of reduction. A better reduction would assert
#   that the rules all agree on the classification. 
#
# We've defined each matching rule to be completely independent. The advantage
# of no stateful processing and no ripple effect from change are central.
# 
# Next, we need to count the events and then normalize those counts into
# something we can display usefully for decision-makers.
#
# Final Velocity Data
# ===================
#
# The details produced by ``action_event_iter()`` are three-tuples of the
# form (action.date, Event, Action).
# Essentially, we have data like this:
#
# +------------+--------+--------+
# | date       | event  | action |
# +------------+--------+--------+
# | yyyy-mm-dd | create | Action |
# |            | remove |        |
# |            | finish |        |
# +------------+--------+--------+
# | yyyy-mm-dd | c/r/f  | Action |
# +------------+--------+--------+
#
# We need to reduce this from individual events to counts of events summarize
# by dates. The first step is to create a ``Counter`` instance using the date and event 
# plucked from each tuple.  We wind up with a ``Dict[Tuple[Date, Event], int]`` structure.
#
# +------------+--------+--------+
# | date       | event  | count  |
# +------------+--------+--------+
# | yyyy-mm-dd | create | int    |
# +------------+--------+--------+
# |            | remove | int    |
# +------------+--------+--------+
# |            | finish | int    |
# +------------+--------+--------+
# | yyyy-mm-dd | create | int    |
# +------------+--------+--------+
# |            | remove | int    |
# +------------+--------+--------+
# |            | finish | int    |
# +------------+--------+--------+
#
# We need to pivot this to a table like this for the final output.
#
# +-------------+--------+--------+--------+
# | date        | create | remove | finish |
# +-------------+--------+--------+--------+
# | yyyy-mm-dd  |  int   |  int   |  int   |
# +-------------+--------+--------+--------+
# | yyyy-mm-dd  |  int   |  int   |  int   |
# +-------------+--------+--------+--------+
# | yyyy-mm-dd  |  int   |  int   |  int   |
# +-------------+--------+--------+--------+
#
# Because we'll be writing to a CSV, this is a ``List[Dict[str, Any]]`` structure.
#
# Normalize By Date
# ------------------
#
# The first step in creating the desired data is to rearrange the ``Counter`` object.
# We want to go from ``Dict[Tuple[Date, Event], int]`` to ``Dict[Date, Dict[Event, int]]``.

def date_by_event(counts: Counter[tuple[Date, Event]]) -> DefaultDict[Date, dict[Event, int]]:
    """
    Normalize to date, and counts for each event type on that date.
    
    :param counts: A Counter organized by a [date, event] key pair.
    :returns: dictionary by date. Each value is a dictionary 
        of {event: count, event: count, ...}
    """
    by_date: DefaultDict[Date, dict[Event, int]] = defaultdict(lambda: defaultdict(int))
    for date, event in counts:
        by_date[date][event] = counts[date, event]
    return by_date
    
# This breaks the functional programming pattern. 
# It doesn't create an iterable sequence of (date, Counter) instances.
# 
# A subsequent step is going to sort this data by date. Creating an iterator
# isn't **strictly** necessary, since an in-memory collection (e.g. dictionary)
# will ultimately be needed.
#
# The SortedContainers provides a handy SortedDict which removes the
# explicit sort step. See http://www.grantjenks.com/docs/sortedcontainers/index.html.
#   
# Convert to Running Counts
# --------------------------
#
# The second step is to convert from daily counts to running counts.
# 
# This algorithm requires sorting by date. It can, therefore, yield
# data as a sequence of row dictionaries with the required data.
#
# From this
#
# ..    code:: python
#
#     {date: {Event.ignore: 2, Event.create: 3, Event.remove: 4}, ...}
#
# To an iterable sequence like this
#
# ..    code:: python
#  
#     (date, {Event.ignore: 2, Event.create: 3, Event.remove: 4})
#     ...
#
# We can formalize the input as ``Dict[Date, Dict[Event, int]]``.
# The output is ``Iterator[Tuple[Date, Dict[Event, int]]``

def running_count_iter(by_date_counter: Dict[Date, Dict[Event, int]]) -> Iterator[Tuple[Date, Counter[Event]]]:
    """
    Convert dict with date keys and sub-dictionaries by event type into
    a sequence of running totals. The sequence can be used to build a 
    new dictionary. Or written to CSV.
    
    :param by_date_counter: Dict[date: Dict[event, int]]
    :returns: a flattened sequence of date, running-total values.
        This can be used to build a dictionary or flattened for CSV output.
    """
    running: Counter[Event] = Counter()
    for d in sorted(by_date_counter):
        for event_type in Event:
            running[event_type] += by_date_counter[d].get(event_type, 0)
        print(d, running.copy())
        yield d, running.copy()
    
# An extension to this can also fill in missing dates to make the plateaus more obvious.
# The iterator would not simply use ``sorted(by_date_counter)``.
# Instead it would iterate from ``min(by_date_counter)`` to a given end date,
# default of today. Each date that had data would lead to an update to running
# values. For all dates (even those with no date) the output would be a copy
# of the counter.
#
# Why is a copy used? We're yielding references to a shared object. If we 
# collect all of this into a single list, it would only show the final running
# count on each item of the list.

# Pivot for CSV Output
# --------------------
#
# The final CSV output can be a dictionary -- for use with a ``DictWriter``.
# Or it can be a simple sequence for use with a ``writer``.
# 
# In this version, we'll create a simple sequence.
#
# From an iterable sequence like this this
#
# ..    code:: python
#    
#      (date, {Event.ignore: 2, Event.create: 3, Event.remove: 4})
#      ...
#        
# To an iterable sequence like this
#
# ..    code:: python
#    
#      [date, 3, 4], 
#      [...]
#
# Or, more formally, from ``Iterator[Tuple[Date, Dict[Event, int]]`` to
# ``Iterator[list[Date, int, ...]]``.

def pivot_for_csv(good_events: list[Event], count_iter: Iterator[Tuple[Date, Counter[Event]]]) -> Iterator[list[Union[Date, int]]]:
    """Flatten for CSV output.
    """
    return (
        cast(List[Union[Date, int]], [date]) + [counts.get(event_type, 0) for event_type in good_events]
        for date, counts in count_iter
    )

# Of course, this can be turned into some separate lambdas to decompose
# the process.
# 
# ..  code:: python
#     
#     date = lambda row: row[0]
#     counts = lambda row: row[1]
#     event_counts = lambda row: counts(row).get(event_type, 0)
#     csv_transform = lambda row: [date(row)] + list(map(event_counts, good_events))
#     map(csv_transform, count_iter)
# 
# The final csv_transform **can** be meaningfully separated from the mapping.
# We might want to use a slightly different transform to create dictionary-based
# row for a ``DictWriter``.
#
# Velocity Computation Wrap-Up
# ----------------------------
#
# We have functions to pivot simple counts with a two-part key (date, event).
# into more useful nested counts with date as a key and then event within each date.
# 
# We can turn date-based mappings of raw counts into running counts, emitting
# a sequence of dates and accumulated totals.
# 
# Finally, we have a function to do a final transformation
# so that is written neatly to a CSV file.
#
# Wait.
#
# Where was the velocity calculated?
#
# Actually. It wasn't.
#
# We emit data with counts by date. We can then use an ordinary least-squares
# tool to compute velocity. The reason why CSV data is the output is (partly)
# to be able to load a spreadsheet with the data and then create charts and 
# graphs in the spreadsheet to annotate progress.
#
# Main Script
# ===========
#
# Let's assemble the pieces. There are four parts:
#
# - `Prepare`_;
# - `Extract`_;
# - `Analyze`_ which includes Transform, Filter, Classify, Reduce; and
# - `Report`_.
# 

if __name__ == "__main__":

# Prepare
# -----------
#
# We'll need the configuration parameters.
# These are required to create the ``TrelloClient`` and the various rules.

    config_filename = "keys.sh"
    config_text = Path(config_filename).read_text()
    config = get_config(config_text)
    
# The client is needed to get the action documents.

    client = TrelloClient(
        api_key=config['TRELLO_API_KEY'],
        api_secret=config['TRELLO_API_SECRET'],
        token=config['OAUTH_TOKEN'],
        token_secret=config['OAUTH_TOKEN_SECRET']
    )

# We'll need to get the ``Board`` object. 
# If the configuration file has a spelling error, we won't find
# the required board. We'll either find too few or too many matches.
# Either of which are a problem.

    boards = list(find_board(client, config['board_name']))
    if len(boards) != 1:
        sys.exit(f"Couldn't find single board {config['board_name']}")
    board = boards[0]
    pprint(board)
        
# Here are the two sets of rules based on reject and finish list names.
# The ``pass_rules`` are used to pass interesting cards.
# The ``action_event_rules`` are used to classify ``Actions`` into ``Events``.

    pass_rules = build_pass_rules(config['reject'].split('|'))
    action_event_rules = build_action_event_rules(config['finished'].split('|'))
    
# Now that everything's set up, we can gather the raw data.
#
# Extract
# ---------
# 
# Here's the data source iterator over the collection of actions.
# The query, ``actions`` is built from the ``action_event_rules`` by taking 
# the first of the args values from each rule three-tuple. 
#
# We might want to clarify this with ``args = lambda rule: rule[1]``.
# This would lead to ``args(a)[0]`` which might be a little less cryptic.
#
# Also, a namedtuple instead of a simple tuple might ne nicer.

    actions = [a[1][0] for a in action_event_rules]
    raw_actions = action_iter(board, actions, limit=1000)

# This doesn't **actually** do anything. It's a generator which will,
# when the values are consumed, emit each raw action document.
# 
# It includes a portion of the Transformation processing, also.
# One could argue that the transformation should be lifted out 
# of the ``action_iter()`` and put into the analysis pipeline.
# This is a relatively simple refactoring, and well worth doing
# to see how flexible functional programming can be.
#
# Analyze
# --------
#
# This encompasses Filtering, Classifying, Reducing, and Pivoting the data.
#
# 1. Filter Actions using PASS_RULES; Classify Events using ACTION_EVENT_RULES.
#
# 2. Reduce to counts with a (date, event type) two-tuple key.
#    Discard the action detail from the classification output.
#
# 3. Restructure counts into a table by date.
#    Each row has an ``{Event: int, ...}`` mapping.
#
# 4. Transform simple by-date counts to running totals.
#    We can, as an extra feature, modify this to add missing dates
#    to show activity plateaus more clearly.
#
# We'll break this down into separate steps. The first two do filtering,
# classifying and reducing to counts. The last two pivot the counts 
# into the desired output structure.

    date_event_action = action_event_iter(pass_rules, action_event_rules, raw_actions)

    date_event_counts = Counter((date, event) for date, event, action in date_event_action)

    date_counts = date_by_event(date_event_counts)
    
    running_totals = running_count_iter(date_counts)
    
# We've filtered, classified, and reduced the raw actions to the running totals.
# We can now report the results in a useful form.
#
# Report
# ---------
#
# We'll write a CSV with only selected summary columns. We compute an ignore
# count, for example, that is not one of the "good" events.

    good_events = list(Event)
    good_events.remove(Event.ignore)
    headers = ['date'] + [et.name for et in good_events]
    
# We overwrite a single file.

    result = Path("counts.csv")
    with result.open('w', newline='') as target:
        writer = csv.writer(target, delimiter='\t')
        writer.writerow(headers)
        writer.writerows(pivot_for_csv(good_events, running_totals))

# Some folks prefer date-stamped output. We can do this pretty easily with 
# some ``f"counts_{now:%Y%m%d}.csv"`` as the filename.
#
# Conclusion
# ==========
#
# We've seen the details of a functional approach to defining processing rules.
# 
# The overall solution decomposes the problem into two broad phases of processing.
#
# - Extract, Transform, Filter, and Classify operations which work on large volumes
#   of data are defined in a functional style. This avoids filling memory with 
#   data sets of an unworkable size.
#
# - After reducing the data to summary counts, a number of functional transformations
#   and pivots can be done to create the desired output. This includes turning simple
#   counts into running totals. This is a stateful transformation and requires a 
#   slightly more complex function definition.
#
# The use of many (many!) small functions and lambdas allows for flexible restructuring
# of the application to do more or different things with the data.
#
# Also, the use of a functional style removes many considerations about the state of
# variables, and the consideration of constraints and invariants.

