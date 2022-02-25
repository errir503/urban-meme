"""Custom data update coordinator for the GitHub integration."""
from __future__ import annotations

from typing import Any

from aiogithubapi import (
    GitHubAPI,
    GitHubConnectionException,
    GitHubException,
    GitHubRatelimitException,
    GitHubResponseModel,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER

GRAPHQL_REPOSITORY_QUERY = """
query ($owner: String!, $repository: String!) {
  rateLimit {
    cost
    remaining
  }
  repository(owner: $owner, name: $repository) {
    default_branch_ref: defaultBranchRef {
      commit: target {
        ... on Commit {
          message: messageHeadline
          url
          sha: oid
        }
      }
    }
    stargazers_count: stargazerCount
    forks_count: forkCount
    full_name: nameWithOwner
    id: databaseId
    watchers(first: 1) {
      total: totalCount
    }
    discussion: discussions(
      first: 1
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      total: totalCount
      discussions: nodes {
        title
        url
        number
      }
    }
    issue: issues(
      first: 1
      states: OPEN
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      total: totalCount
      issues: nodes {
        title
        url
        number
      }
    }
    pull_request: pullRequests(
      first: 1
      states: OPEN
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      total: totalCount
      pull_requests: nodes {
        title
        url
        number
      }
    }
    release: latestRelease {
      name
      url
      tag: tagName
    }
    refs(
      first: 1
      refPrefix: "refs/tags/"
      orderBy: {field: TAG_COMMIT_DATE, direction: DESC}
    ) {
      tags: nodes {
        name
        target {
          url: commitUrl
        }
      }
    }
  }
}
"""


class GitHubDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for the GitHub integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: GitHubAPI,
        repository: str,
    ) -> None:
        """Initialize GitHub data update coordinator base class."""
        self.repository = repository
        self._client = client
        self._last_response: GitHubResponseModel[dict[str, Any]] | None = None
        self.data = {}

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> GitHubResponseModel[dict[str, Any]]:
        """Update data."""
        owner, repository = self.repository.split("/")
        try:
            response = await self._client.graphql(
                query=GRAPHQL_REPOSITORY_QUERY,
                variables={"owner": owner, "repository": repository},
            )
        except (GitHubConnectionException, GitHubRatelimitException) as exception:
            # These are expected and we dont log anything extra
            raise UpdateFailed(exception) from exception
        except GitHubException as exception:
            # These are unexpected and we log the trace to help with troubleshooting
            LOGGER.exception(exception)
            raise UpdateFailed(exception) from exception
        else:
            self._last_response = response
            return response.data["data"]["repository"]
