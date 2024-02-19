from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List, Union, cast
from urllib.parse import urljoin, urlparse

from w3lib.url import safe_url_string

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import HtmlResponse, Response
from scrapy.settings import BaseSettings
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.response import get_meta_refresh

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

logger = logging.getLogger(__name__)
coverage_matrix = [False] * 11 #10 interest points 


def _build_redirect_request(
    source_request: Request, *, url: str, **kwargs: Any
) -> Request:
    redirect_request = source_request.replace(
        url=url,
        **kwargs,
        cookies=None,
    )
    has_cookie_header = "Cookie" in redirect_request.headers
    has_authorization_header = "Authorization" in redirect_request.headers
    if has_cookie_header or has_authorization_header:
        source_request_netloc = urlparse_cached(source_request).netloc
        redirect_request_netloc = urlparse_cached(redirect_request).netloc
        if source_request_netloc != redirect_request_netloc:
            if has_cookie_header:
                del redirect_request.headers["Cookie"]
            # https://fetch.spec.whatwg.org/#ref-for-cors-non-wildcard-request-header-name
            if has_authorization_header:
                del redirect_request.headers["Authorization"]
    return redirect_request


class BaseRedirectMiddleware:
    enabled_setting: str = "REDIRECT_ENABLED"

    def __init__(self, settings: BaseSettings):
        if not settings.getbool(self.enabled_setting):
            raise NotConfigured

        self.max_redirect_times: int = settings.getint("REDIRECT_MAX_TIMES")
        self.priority_adjust: int = settings.getint("REDIRECT_PRIORITY_ADJUST")

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings)

    def _redirect(
        self, redirected: Request, request: Request, spider: Spider, reason: Any
    ) -> Request:
        ttl = request.meta.setdefault("redirect_ttl", self.max_redirect_times)
        redirects = request.meta.get("redirect_times", 0) + 1

        if ttl and redirects <= self.max_redirect_times:
            redirected.meta["redirect_times"] = redirects
            redirected.meta["redirect_ttl"] = ttl - 1
            redirected.meta["redirect_urls"] = request.meta.get("redirect_urls", []) + [
                request.url
            ]
            redirected.meta["redirect_reasons"] = request.meta.get(
                "redirect_reasons", []
            ) + [reason]
            redirected.dont_filter = request.dont_filter
            redirected.priority = request.priority + self.priority_adjust
            logger.debug(
                "Redirecting (%(reason)s) to %(redirected)s from %(request)s",
                {"reason": reason, "redirected": redirected, "request": request},
                extra={"spider": spider},
            )
            return redirected
        logger.debug(
            "Discarding %(request)s: max redirections reached",
            {"request": request},
            extra={"spider": spider},
        )
        raise IgnoreRequest("max redirections reached")

    def _redirect_request_using_get(
        self, request: Request, redirect_url: str
    ) -> Request:
        redirect_request = _build_redirect_request(
            request,
            url=redirect_url,
            method="GET",
            body="",
        )
        redirect_request.headers.pop("Content-Type", None)
        redirect_request.headers.pop("Content-Length", None)
        return redirect_request


class RedirectMiddleware(BaseRedirectMiddleware):
    """
    Handle redirection of requests based on response status
    and meta-refresh html tag.
    """

    def get_coverage_process_response(self) : 
        return coverage_matrix
    
    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Union[Request, Response]:
        coverage_matrix[0] = True
        if ( 
            request.meta.get("dont_redirect", False)
            or response.status in getattr(spider, "handle_httpstatus_list", [])
            or response.status in request.meta.get("handle_httpstatus_list", [])
            or request.meta.get("handle_httpstatus_all", False)
        ): # 1-4
            if(request.meta.get("dont_redirect", False)): 
                coverage_matrix[1] = True
            elif(response.status in getattr(spider, "handle_httpstatus_list", [])) : 
                coverage_matrix[2] = True
            elif(response.status in request.meta.get("handle_httpstatus_list", [])) : 
                coverage_matrix[3] = True
            elif(request.meta.get("handle_httpstatus_all", False)): 
                coverage_matrix[4] = True

            return response # s=1

        allowed_status = (301, 302, 303, 307, 308)
        if "Location" not in response.headers or response.status not in allowed_status: # 5-6
            if("Location" not in response.headers): 
                coverage_matrix[5] = True
            elif(response.status not in allowed_status) : 
                coverage_matrix[6] = True

            return response # s=2

        assert response.headers["Location"] is not None
        location = safe_url_string(response.headers["Location"])

        if response.headers["Location"].startswith(b"//"): # 7
            coverage_matrix[7] = True
            request_scheme = urlparse(request.url).scheme
            location = request_scheme + "://" + location.lstrip("/")

        redirected_url = urljoin(request.url, location)

        if response.status in (301, 307, 308) or request.method == "HEAD":# 8-9
            if(response.status in (301, 307, 308)) : 
                coverage_matrix[8] = True
            elif(request.method == "HEAD") : 
                coverage_matrix[9] = True
            redirected = _build_redirect_request(request, url=redirected_url)
            return self._redirect(redirected, request, spider, response.status) # s=3

        coverage_matrix[10] = True
        redirected = self._redirect_request_using_get(request, redirected_url)
        return self._redirect(redirected, request, spider, response.status) #s=4
    
    #Total CCN = 9 - 4 + 2 = 7 (10 according to lizard)

class MetaRefreshMiddleware(BaseRedirectMiddleware):
    enabled_setting = "METAREFRESH_ENABLED"

    def __init__(self, settings: BaseSettings):
        super().__init__(settings)
        self._ignore_tags: List[str] = settings.getlist("METAREFRESH_IGNORE_TAGS")
        self._maxdelay: int = settings.getint("METAREFRESH_MAXDELAY")

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Union[Request, Response]:
        if (
            request.meta.get("dont_redirect", False)
            or request.method == "HEAD"
            or not isinstance(response, HtmlResponse)
        ):
            return response

        interval, url = get_meta_refresh(response, ignore_tags=self._ignore_tags)
        if url and cast(float, interval) < self._maxdelay:
            redirected = self._redirect_request_using_get(request, url)
            return self._redirect(redirected, request, spider, "meta refresh")

        return response
