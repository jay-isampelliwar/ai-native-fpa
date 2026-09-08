"""The rule that keeps a conversational answer honest: only the figures a skill returned.

The model that talks to a person can see what the skills computed, and is told to quote those figures
and never to calculate. This is the part that does not depend on it complying. Every number in the
reply is compared against the numbers in what the tools returned and in what the person themselves
said, and a reply carrying anything else is discarded in favour of the skill's own sentence.

Both directions are tested, because a check that only ever passes is indistinguishable from no
check. The reformatting case is the one worth keeping: "2.26 lakh" is the same amount as "226,000"
and is rejected anyway, since a model that may reformat a figure may reformat it wrongly and there
is a correct sentence to fall back to.
"""

from app.agent.narration import figures_in, invents_figures


def test_grouping_and_currency_are_not_part_of_a_number():

    """A figure is the same figure however it is written, or the check would fire on formatting alone."""

    assert figures_in("INR 226,000") == figures_in("226000")

    assert figures_in("You have 12 records and INR 1,500 left") == {"12", "1500"}


def test_a_reply_quoting_what_a_skill_returned_is_kept():

    """The ordinary case: the model repeats the computed figures in its own words."""

    answer = "Income this month is INR 226,000. Committed outflow is INR 250,000."

    assert not invents_figures("You brought in INR 226,000 and INR 250,000 went out.", [answer])


def test_a_total_nobody_computed_is_caught():

    """A difference the model worked out itself is exactly what no reply may contain."""

    answer = "Income this month is INR 226,000. Committed outflow is INR 250,000."

    assert invents_figures("You are INR 24,000 short this month.", [answer])


def test_a_reformatted_figure_is_caught_too():

    """Right amount, different string: rejected, because reformatting correctly is not guaranteed."""

    assert invents_figures("You earn about 2.26 lakh a month.", ["Income this month is INR 226,000."])


def test_a_figure_the_person_stated_is_theirs_to_repeat():

    """Someone who says what they earn should be answered with it, without the planner claiming to have computed it."""

    assert not invents_figures("So that is INR 150,000 a month coming in.", ["", "my salary is INR 150,000 a month"])


def test_a_reply_with_no_figures_is_always_fine():

    """Most of a conversation quotes nothing, and none of it should be blocked by a rule about numbers."""

    assert not invents_figures("Tell me what you earn and I will start from there.", [])
