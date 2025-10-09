"""Run definitions that are part of code productionalisation"""

from projspec.content import BaseContent


class GithubAction(BaseContent):
    """A run prescription that runs in github on push/merge"""

    # TODO: we probably want to extract out the jobs and runs, maybe the steps.
    #  It may be interesting to provide links to the browser or API to view
    #  details.
    ...


# TODO: there are many of these, but we don't extract much information from them
