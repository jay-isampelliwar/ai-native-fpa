"""The user ids demo and test data belong to, kept far away from the ones a person might type.

Identity in this phase is an integer someone enters at a gate, and the seeded fixtures took 1 and 2 -
the two ids anybody trying the product picks first. So the fixtures and real use collided: a person
signing in as 1 saw seeded records mixed with their own, and the moment they added a record as user
2 the repository test asserting "user 2 has no records" began failing on a fact about their data
rather than about the code.

Six figure ids solve it by being implausible to type. Nothing enforces the separation - there is no
reserved range in the database - so the protection is only that nobody chooses 990001 by accident,
which is enough for a phase with no accounts.

Both the SQL seeder and the in memory repositories import these, because the two must agree: the
backend parity tests read the same records from each and would otherwise be comparing different
people.
"""

SEED_USER_ID = 990001

SECOND_SEED_USER_ID = 990002
