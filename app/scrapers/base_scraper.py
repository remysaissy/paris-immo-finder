import logging
import sys
import time
import traceback
from weakref import WeakValueDictionary


import bs4
from selenium import webdriver

from app.services import slack
from app.utils import db


class BaseScraper(object):
    """ Abstract class for implementing a datasource. """

    _instances = WeakValueDictionary()

    def __init__(self):
        self._instances[id(self)] = self
        self.logger = logging.getLogger()
        self.__browser = webdriver.PhantomJS(service_args=['--load-images=no', '--disk-cache=true'])
        # self.__browser = webdriver.Chrome()
        # self.__browser.set_window_size(1280, 1024)
        # self.__browser.implicitly_wait(10)
        # self.__browser.set_page_load_timeout(60)

    def __del__(self):
        self.__browser.quit()

# region scraping methods
    def _get_search_url(self):
        """
         The search url of the datasource
         :return string
        """
        NotImplementedError("Class {} doesn't implement aMethod()".format(self.__class__.__name__))

    def _get_offers(self, root):
        """
         Builds a list of offers
         :return list(Offer)
        """
        NotImplementedError("Class {} doesn't implement aMethod()".format(self.__class__.__name__))

    def __get_offers(self, root):
        """
         Builds a list of offers
         :return list(BaseOffer)
        """
        offers = []
        r_offers = self._get_offers(root)
        for r_offer in r_offers:
            o = self._get_offer_object(r_offer)
            if o is None:
                continue
            if self._is_valid_offer(o, r_offer):
                payload = self._prepare_offer_filling(o, r_offer)
                o.fill_object(self, r_offer, payload)
                self._clean_offer_filling(o, r_offer, payload)
                offers.append(o)
            else:
                self.logger.warning("Invalid offer detected. Skipping...")
        return offers

    def _get_offer_object(self, r_offer):
        """
         Returns a valid offer object for the offer to parse.
         :return A BaseOffer object subclass instance
        """
        NotImplementedError("Class {} doesn't implement aMethod()".format(self.__class__.__name__))

    def _is_valid_offer(self, offer, r_offer):
        """
         Let the datasource object checks if the offer to be parsed is a valid one.
         If the validity check allows to prefill some fields, the offer model object can be used.
         :return True if the offer is valid, False otherwise
        """
        NotImplementedError("Class {} doesn't implement aMethod()".format(self.__class__.__name__))

    def _prepare_offer_filling(self, offer, r_offer):
        """
         Let the datasource object preloads required state to fill the offer object.
         The offer object can already be filled with some properties to avoid duplicate lookups in r_offers.
         :return a payload of any data useful for the offer filling
        """
        NotImplementedError("Class {} doesn't implement aMethod()".format(self.__class__.__name__))

    def _clean_offer_filling(self, offer, r_offer, payload):
        """
         Let the datasource object clean up its state.
         At the time of calling, the offer object must not be modified.
        """
        NotImplementedError("Class {} doesn't implement aMethod()".format(self.__class__.__name__))

    def _has_next_page(self, root):
        """
            Check if there is a next page and returns it parameters.
             :returns has_next_page(bool),url(string),params(dict)
        """
        NotImplementedError("Class {} doesn't implement aMethod()".format(self.__class__.__name__))

    def _load_web_page(self, url):
        """
         Retrieves results and returns a ready to use return object
         :return BeautifulSoup instance.
        """
        self.__browser.get(url)  # This does not throw an exception if it got a 404
        html = self.__browser.page_source
        self.logger.info("GET request: {}".format(url))
        result = None
        try:
            result = bs4.BeautifulSoup(html, 'html5lib')
        except Exception as e:
            self.logger.error("Failed to load webpage {}: {}".format(url, str(e)))
        finally:
            return result

    def _next_page(self):
        """ Retrieve the next page of results. This method must yield each page.
          :return list[Offer]: A list of Offer objects.
        """
        has_next = True
        url = self._get_search_url()
        while has_next:
            root = self._load_web_page(url)
            if root is not None:
                has_next, url = self._has_next_page(root)
                yield self.__get_offers(root)

    @classmethod
    def get_or_none(cls, obj, key):
        val = obj.find(key)
        if val is not None:
            val = val.text
        return val

# endregion


# region datasource identification and scrape methods
    def get_datasource_name(self):
        """ Returns the datasource's name. """
        return self.__class__.__name__

    def scrape(self):
        """ Runs the datasource. """
        self.logger.info("{}: Retrieving offers from {}...".format(time.ctime(), self.get_datasource_name()))
        try:
            total_count = 0
            for offers in self._next_page():
                for o in offers:
                    if db.Offer.is_new_offer(o, self.get_datasource_name()):
                        db.Offer.persist_offer(o, self.get_datasource_name())
                    # if db.Offer.is_new_offer(o, self.get_datasource_name()) and filter.Filter.apply(o) is False:
                    #     db.Offer.persist_offer(o, self.get_datasource_name())
                        slack.Slack.post_message(o)
                        total_count += 1
        except Exception as exc:
            self.logger.error("Error with the scraping:", sys.exc_info()[0])
            traceback.print_exc()
        else:
            self.logger.info("{}: Got {} results from {}".format(time.ctime(), total_count, self.get_datasource_name()))

# endregion

# region field extraction methods

# endregion
