#######################################################
Literate, Functional Python: Agile Velocity from Trello
#######################################################

The app helps with "burn-up" charting to compute two velocities:

1.  New cards made.

2.  Cards moved to a "finished" column (or closed.)

Ideally, these two converge. If they don't, you have problems.

More fundamentally, this is a tutorial of sorts that attempts
to  illustrate two things:

-   The functional approach to using Python for ETL and
    analytics. This can process a **large** number of Trello actions because it
    avoids large in-memory data structures.
    
-   An exercise written in a literate style. The source is 
    actually an RST file that generates working code and documentation
    from a single source.
    
The goal is to provide a starter kit for functional python or literate programming.

You'll need a Trello board to analyze. Now's a good time to create a project 
for yourself. http://trello.com

If you're using some other board, you'll have to change the low-level access
module from ``py-trello`` to another driver, or perhaps you'll have to create
your own using ``requests``.

Install
=======

This uses Python 3.6. You can tweak the app to run in Python 3.5.

If you have Python 3.6, away you go.

If you don't yet have Python 3.6, you have two choices.

-   Upgrade now.

-   Use conda to create a Python 3.6 environment. Start here: https://conda.io/docs/index.html

    ::
    
        conda create --name litfunc python=3.5
        source activate litfunc

Install the supporting code. Two choices.

-   pip

    ::

        pip install py-trello
        pip install pylit3
        
-   conda

    ::
    
        conda install py-trello
        conda install pylit3
    
Finally. Check out the the Trello-Action-Counts repository from Git Hub.

You could install it, but that's not really the point. The point
is to use this as an example for understanding functional Python
or literate programming (or both.)

You'll be playing with the source to explore design alternatives.

Setup Trello Keys
=================

Visit https://trello.com/1/appKey/generate to get the
TRELLO_API_KEY and TRELLO_API_SECRET.

Create a little configuration file with a name like ``keys.sh``.

::

    export TRELLO_API_KEY=...
    export TRELLO_API_SECRET=...
    
Source this file to set the two environment variables.
Run the following program to get the OAUTH token.

::

    $ python3.6 -m trello.util
    Request Token:
        - oauth_token        = ...
        - oauth_token_secret = ...

    Go to the following link in your browser:
    https://trello.com/1/OAuthAuthorizeToken?oauth_token=...&scope=read,write&expiration=30days&name=py-trello

The browser will display a PIN

::

    Have you authorized me? (y/n) y
    What is the PIN? ...
    Access Token:
        - oauth_token        = ...
        - oauth_token_secret = ...

    You may now access protected resources using the access tokens above.

Update your ``keys.sh`` with the two additional fields. Uppercase the names.
It will look like this:

::

    export TRELLO_API_KEY=...
    export TRELLO_API_SECRET=...
    export OAUTH_TOKEN=...
    export OAUTH_TOKEN_SECRET=...

This is the base configuration file required by the Trello-Velocity app.
    
Using the Trello Action Counts App
==================================

Configure the ``keys.sh`` file.

Run the app.

Open the CSV in your favorite spreadsheet.

Configuration
-------------

Build the final the ``keys.sh`` configuration file with parameters based 
on your Trello board. 

::

    export board_name=Your Board Name
    export reject=Reference|Background
    export finished=Completed|Approved
    
The ``board_name`` is the name of the board to search for. This must be 
a unique beginning of the board's name.

The ``reject`` value is a |-separated list of list names which are ignored.

The ``finished`` value is a |-separated list of list names which indicated "completed".

The counts will ignore all cards in the reject lists. The create count
and remove count apply to all remaining lists. The finish count is for
cards moved to the finish list or otherwise closed.

Run The App
-----------

::

    slott$ python3.6 action_counts.py

This displays log that shows the date-level running totals. It should confirm
that you're seeing data from your selected board and cards. If not, you can use 
this module to write some little exploration programs

It also writes a ``counts.csv`` with the data in a form that's more useful.

About the Counts
----------------

We count Actions related to Cards where the action indicates a story
was created or completed. We ignore several actions.

New Stories:
-   'copyCard'
-   'createCard'
-   'moveCardToBoard'

Removed Stories:
-   'deleteCard'
-   'moveCardToBoard'

Completed Stories:
-   'updateCard:closed'
-   'updateCard:idList' for a specific "done" list.

We don't look at checklists within a card. That's an interesting extension.

Data Exploration
----------------

There are a few other possibly useful functions that may help locate the 
boards and lists of interest.

-   ``board_list(client)`` -- lists all boards.

-   ``list_list(client, board_name)`` -- list of all lists on a given board.


Literate Programming
====================

The PyLit-3 approach to Literate Programming is to have two versions of the source.

-   An RST-format file. This can be used to produce pure Python code as well
    as documentation in any of the formats supported by docutils.
    
-   The Python file. This can be used to create the RST-format file, which can
    then be used to create documentation.
    
The point is that the source code **is** the basis for the documentation.

Here's how to turn the ``.py`` file into ``.py.txt`` and the ``docs/*.html``

::

    slott$ python3.6 -m pylit --codeindent=4 -c action_counts.py
    extract written to action_counts.py.txt
    slott$ rst2html.py --stylesheet=docs/slott.css action_counts.py.txt docs/action_counts.html

The pylit program can also transform the ``.py.txt`` into the ``.py`` as well
as the ``docs/*.html``. There are a number of possible changes to the style options
that can be used to create different HTML representations.

Also, pylit can be used to run the built-in doctest examples in the documentation.

::

    slott$ python3.6 -m pylit --doctest action_counts.py
    0 failures in 23 tests

Feel free to add tests as needed.
