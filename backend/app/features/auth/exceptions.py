"""Errors the auth service raises for the route to turn into HTTP responses."""


class EmailTaken(Exception):

    """Another user already signed up with this email."""


class InvalidCredentials(Exception):

    """The email is unknown or the password does not match."""
