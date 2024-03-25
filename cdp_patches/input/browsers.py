from contextlib import suppress
from datetime import datetime
from typing import Dict, List, TypedDict, Union

from playwright.async_api import Browser as AsyncBrowser
from playwright.async_api import BrowserContext as AsyncContext
from playwright.async_api import Error as AsyncError
from playwright.async_api import Error as SyncError
from playwright.sync_api import Browser as SyncBrowser
from playwright.sync_api import BrowserContext as SyncContext
from selenium import webdriver
from selenium_driverless import webdriver as driverless_async_webdriver
from selenium_driverless.sync import webdriver as driverless_sync_webdriver

all_browsers = Union[webdriver.Chrome, SyncContext, SyncBrowser, AsyncContext, AsyncBrowser, driverless_sync_webdriver.Chrome, driverless_async_webdriver.Chrome]
sync_browsers = Union[webdriver.Chrome, SyncContext, SyncBrowser, driverless_sync_webdriver.Chrome]
async_browsers = Union[AsyncContext, AsyncBrowser, driverless_async_webdriver.Chrome]


class InternalProcessInfo(TypedDict):
    type: str
    id: int
    cpuTime: float


class CDPProcessInfo:
    processInfo: List[InternalProcessInfo]

    def __init__(self, process_info: Dict[str, List[InternalProcessInfo]]) -> None:
        self.processInfo = process_info["processInfo"]

    def get_main_browser(self) -> InternalProcessInfo:
        for process in self.processInfo:
            if process.get("type") == "browser":
                return process

        raise ValueError("No browser process found.")


# Browser PID
# Selenium & Selenium Driverless
def get_sync_selenium_browser_pid(driver: Union[webdriver.Chrome, driverless_sync_webdriver.Chrome]) -> int:
    if isinstance(driver, driverless_sync_webdriver.Chrome):
        cdp_system_info = driver.base_target.execute_cdp_cmd(cmd="SystemInfo.getProcessInfo")
    else:
        cdp_system_info = driver.execute_cdp_cmd(cmd="SystemInfo.getProcessInfo", cmd_args={})

    process_info = CDPProcessInfo(cdp_system_info)
    browser_info = process_info.get_main_browser()
    return browser_info["id"]


async def get_async_selenium_browser_pid(driver: driverless_async_webdriver.Chrome) -> int:
    cdp_system_info = await driver.base_target.execute_cdp_cmd(cmd="SystemInfo.getProcessInfo")

    process_info = CDPProcessInfo(cdp_system_info)
    browser_info = process_info.get_main_browser()
    return browser_info["id"]


# Playwright
def get_sync_playwright_browser_pid(browser: Union[SyncContext, SyncBrowser]) -> int:
    if isinstance(browser, SyncContext):
        main_browser = browser.browser
        assert main_browser
        cdp_session = main_browser.new_browser_cdp_session()
    elif isinstance(browser, SyncBrowser):
        cdp_session = browser.new_browser_cdp_session()
    else:
        raise ValueError("Invalid browser type.")

    cdp_system_info = cdp_session.send("SystemInfo.getProcessInfo")

    process_info = CDPProcessInfo(cdp_system_info)
    browser_info = process_info.get_main_browser()
    return browser_info["id"]


async def get_async_playwright_browser_pid(browser: Union[AsyncContext, AsyncBrowser]) -> int:
    if isinstance(browser, AsyncContext):
        main_browser = browser.browser
        assert main_browser
        cdp_session = await main_browser.new_browser_cdp_session()
    elif isinstance(browser, AsyncBrowser):
        cdp_session = await browser.new_browser_cdp_session()
    else:
        raise ValueError("Invalid browser type.")
    cdp_system_info = await cdp_session.send("SystemInfo.getProcessInfo")

    process_info = CDPProcessInfo(cdp_system_info)
    browser_info = process_info.get_main_browser()
    return browser_info["id"]


def get_sync_browser_pid(browser: sync_browsers) -> int:
    if isinstance(browser, webdriver.Chrome) or isinstance(browser, driverless_sync_webdriver.Chrome):
        return get_sync_selenium_browser_pid(browser)
    elif isinstance(browser, SyncContext) or isinstance(browser, SyncBrowser):
        return get_sync_playwright_browser_pid(browser)

    raise ValueError("Invalid browser type.")


async def get_async_browser_pid(browser: async_browsers) -> int:
    if isinstance(browser, driverless_async_webdriver.Chrome):
        return await get_async_selenium_browser_pid(browser)
    elif isinstance(browser, AsyncContext) or isinstance(browser, AsyncBrowser):
        return await get_async_playwright_browser_pid(browser)

    raise ValueError("Invalid browser type.")


# Scale Factor
# Selenium & Selenium Driverless
def get_sync_selenium_scale_factor(driver: Union[webdriver.Chrome, driverless_sync_webdriver.Chrome]) -> int:
    if isinstance(driver, driverless_sync_webdriver.Chrome):
        _scale_factor: int = driver.execute_script("return window.devicePixelRatio", unique_context=True)
        return _scale_factor

    scale_factor: int = driver.execute_script("return window.devicePixelRatio")
    return scale_factor


async def get_async_selenium_scale_factor(driver: driverless_async_webdriver.Chrome) -> int:
    scale_factor: int = await driver.execute_script("return window.devicePixelRatio", unique_context=True)
    return scale_factor


# Playwright with Runtime Patching
def get_sync_playwright_scale_factor(browser: Union[SyncContext, SyncBrowser]) -> int:
    close_context, close_page = False, False
    if isinstance(browser, SyncContext):
        context = browser
    elif isinstance(browser, SyncBrowser):
        if any(browser.contexts):
            context = browser.contexts[0]
        else:
            context = browser.new_context()
            close_context = True
    else:
        raise ValueError("Invalid browser type.")

    if any(context.pages):
        page = context.pages[0]
    else:
        page = context.new_page()
        close_page = True
    cdp_session = context.new_cdp_session(page)

    time1 = datetime.now()
    while (datetime.now() - time1).seconds <= 10:
        try:
            page_frame_tree = cdp_session.send("Page.getFrameTree")
            page_id = page_frame_tree["frameTree"]["frame"]["id"]

            isolated_world = cdp_session.send("Page.createIsolatedWorld", {"frameId": page_id, "grantUniveralAccess": True, "worldName": "Shimmy shimmy yay, shimmy yay, shimmy ya"})
            isolated_exec_id = isolated_world["executionContextId"]
            break
        except SyncError as e:
            if e.message == "Protocol error (Page.createIsolatedWorld): Invalid parameters":
                pass
            else:
                raise e
    else:
        raise TimeoutError("Page.createIsolatedWorld did not initialize properly within 30 seconds.")

    time2 = datetime.now()
    while (datetime.now() - time2).seconds <= 10:
        try:
            scale_factor_eval = cdp_session.send("Runtime.evaluate", {"expression": "window.devicePixelRatio", "contextId": isolated_exec_id})
            scale_factor: int = scale_factor_eval["result"]["value"]
            break
        except SyncError as e:
            if e.message == "Protocol error (Runtime.evaluate): Cannot find context with specified id":
                pass
            else:
                raise e
    else:
        raise TimeoutError("Runtime.evaluate did not run properly within 30 seconds.")

    with suppress(SyncError):
        if close_page:
            page.close()

    with suppress(SyncError):
        if close_context:
            context.close()

    return scale_factor


async def get_async_playwright_scale_factor(browser: Union[AsyncContext, AsyncBrowser]) -> int:
    close_context, close_page = False, False
    if isinstance(browser, AsyncContext):
        context = browser
    elif isinstance(browser, AsyncBrowser):
        if any(browser.contexts):
            context = browser.contexts[0]
        else:
            context = await browser.new_context()
            close_context = True
    else:
        raise ValueError("Invalid browser type.")

    if any(context.pages):
        page = context.pages[0]
    else:
        page = await context.new_page()
        close_page = True
    cdp_session = await context.new_cdp_session(page)

    time1 = datetime.now()
    while (datetime.now() - time1).seconds <= 10:
        try:
            page_frame_tree = await cdp_session.send("Page.getFrameTree")
            page_id = page_frame_tree["frameTree"]["frame"]["id"]

            isolated_world = await cdp_session.send("Page.createIsolatedWorld", {"frameId": page_id, "grantUniveralAccess": True, "worldName": "Shimmy shimmy yay, shimmy yay, shimmy ya"})
            isolated_exec_id = isolated_world["executionContextId"]
            break
        except AsyncError as e:
            if e.message == "Protocol error (Page.createIsolatedWorld): Invalid parameters":
                pass
            else:
                raise e
    else:
        raise TimeoutError("Page.createIsolatedWorld did not initialize properly within 30 seconds.")

    time2 = datetime.now()
    while (datetime.now() - time2).seconds <= 10:
        try:
            scale_factor_eval = await cdp_session.send("Runtime.evaluate", {"expression": "window.devicePixelRatio", "contextId": isolated_exec_id})
            scale_factor: int = scale_factor_eval["result"]["value"]
            break
        except AsyncError as e:
            if e.message == "Protocol error (Runtime.evaluate): Cannot find context with specified id":
                pass
            else:
                raise e
    else:
        raise TimeoutError("Runtime.evaluate did not run properly within 30 seconds.")

    with suppress(SyncError):
        if close_page:
            await page.close()

    with suppress(SyncError):
        if close_context:
            await context.close()

    return scale_factor


def get_sync_scale_factor(browser: sync_browsers) -> int:
    if isinstance(browser, webdriver.Chrome) or isinstance(browser, driverless_sync_webdriver.Chrome):
        return get_sync_selenium_scale_factor(browser)
    elif isinstance(browser, SyncContext) or isinstance(browser, SyncBrowser):
        return get_sync_playwright_scale_factor(browser)

    raise ValueError("Invalid browser type.")


async def get_async_scale_factor(browser: async_browsers) -> int:
    if isinstance(browser, driverless_async_webdriver.Chrome):
        return await get_async_selenium_scale_factor(browser)
    elif isinstance(browser, AsyncContext) or isinstance(browser, AsyncBrowser):
        return await get_async_playwright_scale_factor(browser)

    raise ValueError("Invalid browser type.")
