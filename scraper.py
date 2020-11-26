#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Methods to get tweets and convert then into a parsable feed.
"""
import requests \
    , re \
    , logging \
    , json \
    , ssl

from tqdm import tqdm
from datetime import datetime
from bs4 import BeautifulSoup


class Scraper:
    #######################
    # Authorization tokens

    """
    URL pointing to the file where we can obtain the bearer token
    """
    BEARER_TOKEN_URL = "https://abs.twimg.com/responsive-web/client-web/main.a8574df5.js"
    BEARER_TOKEN = None

    """
    Endpoint where we can request a guest token, which has to be provided to interact
    with the REST API.
    This endpoints responds to a POST with the BEARER_TOKEN header.
    """
    GUEST_TOKEN_URL = "https://api.twitter.com/1.1/guest/activate.json"
    GUEST_TOKEN = None

    #
    #######################

    """
    URL to get a user's REST id
    """
    build_user_info_url = lambda s, handle: "https://api.twitter.com/graphql/" \
                                            + "4S2ihIKfF3xhp-ENxvUAfQ/UserByScreenName?variables=%7B%22screen_name%22%3A%22" \
                                            + handle + "%22%2C%22withHighlightedLabel%22%3Atrue%7D"

    """
    Main URL to get the first page of tweets, knowing the user's rest_id, which can be
    obtained with get_user_rest_id()
    """
    build_twitter_url = lambda s, rest_id, count: "https://api.twitter.com/2/timeline/profile/" \
                                                  + rest_id + ".json" \
                                                  + "?include_profile_interstitial_type=1" \
                                                  + "&include_blocking=1" \
                                                  + "&include_blocked_by=1" \
                                                  + "&include_followed_by=1" \
                                                  + "&include_want_retweets=1" \
                                                  + "&include_mute_edge=1" \
                                                  + "&include_can_dm=1" \
                                                  + "&include_can_media_tag=1" \
                                                  + "&skip_status=1" \
                                                  + "&cards_platform=Web-12" \
                                                  + "&include_cards=1" \
                                                  + "&include_ext_alt_text=true" \
                                                  + "&include_quote_count=true" \
                                                  + "&include_reply_count=1" \
                                                  + "&tweet_mode=extended" \
                                                  + "&include_entities=true" \
                                                  + "&include_user_entities=true" \
                                                  + "&include_ext_media_color=true" \
                                                  + "&include_ext_media_availability=true" \
                                                  + "&send_error_codes=true" \
                                                  + "&simple_quoted_tweet=true" \
                                                  + "&include_tweet_replies=false" \
                                                  + "&userId=" + rest_id \
                                                  + "&count=" + str(count) \
                                                  + "&ext=mediaStats%2ChighlightedLabel"

    """
    Builds the URL to get the rest of the tweets, knowing the max_position
    """
    build_newpage_url = lambda _, user, max_pos: "https://twitter.com/i/profiles/show/" \
                                                 + user + "/timeline/tweets?" \
                                                 + "include_available_features=1&include_entities=1" \
                                                 + "&max_position=" + str(max_pos) + "&reset_error_state=false"

    """
    Builds the URL to get the new tweets, knowing the min_position
    """
    build_update_url = (
        lambda user
               , min_pos:
        "https://twitter.com/i/profiles/show/" + user + "/timeline/tweets?"
        + "composed_count=0&include_available_features=1&"
        + "include_entities=1&include_new_items_bar=true&"
        + "interval=30000&latent_count=0&min_position=" + str(min_pos)
    )

    """
    Seconds before giving up on the URL request
    """
    timeout = 20

    """
    Main object with all the information from the users

    This object has the structure defined in the README.md:

    {
        "<user handle>": {
            "id": "<user ID>"
            , "rest_id": "<user ID to perform API requests>"
            , "tweets": [
                {
                    "tweet_id": "<tweet-id>"
                    , "profile_pic": "<avatar URL of the tweet owner>"
                    , "permalink": "<link to the tweet>"
                    , "stats": {
                          "likes": <number of likes>
                        , "retweets": <number of retweets>
                        , "replies": <number of replies>
                    }
                    , "text": "<plain text of the tweet>"
                    , "tweet_age": <(NUM) timestamp of the tweet, in UNIX epoch format>
                    , "pinned": <BOOL>
                    , "conversation": <conversation-id>
                    , "user": {
                        # Information of the owner of the tweet (important if it's a retweet)
                          "username": <account name (twitter.com/username)>
                        , "displayname": <nickname for the user>
                        , "uid": <user id>
                        , "avatar": <profile pic>
                    }
                    , "retweet": <indication to know if it's a retweet>
                    # Only if "retweet" is True
                    , "retweet_info" {
                          "retweet_id": <id of the retweet>
                        , "retweeter": <username who retweeted (the one whose data is being extracted)>
                    }
                }
            # ... (more tweeets from the user)
            ]
            , "cursor": {
                "top": "<ID of the most recent tweet recovered>"
                , "bottom": "<ID of the oldest tweet recovered>"
            }
        }
        # ... (more users and their tweets)
    }
    """
    scraped_info = {}

    def __init__(self):
        """
        Initializes the authorization tokens.
        """
        logger = logging.getLogger(__name__ + ".init")

        logger.info("Initializing authorization data")
        logger.info("Obtaining bearer token via GET " + self.BEARER_TOKEN_URL)

        try:
            response = requests.get(self.BEARER_TOKEN_URL, timeout=self.timeout).text
        except Exception as e:
            logger.error("Failed to get bearer token => " + str(e))
            return

        # The token is initialized (hard-coded?) as variable 'a', and is 104 characters
        # long. This should be enough to obtain the right token, I guess...
        token = re.findall(r'a="[A-Za-z0-9%]{104}"', response)

        if len(token) != 1:
            logger.info("Expected only one match, but got: " + token)
            return

        # Removes a=" (3 chars) at the beginning and " (One char) at the end
        self.BEARER_TOKEN = token[0][3:-1]
        logger.info("Got bearer token: " + self.BEARER_TOKEN)

        ####
        # Now, gets the x-guest-token
        ####
        logger.info("Obtaining x-guest-token via POST " + self.GUEST_TOKEN_URL)

        try:
            headers = {"Authorization": "Bearer " + self.BEARER_TOKEN}
            response = requests.post(self.GUEST_TOKEN_URL
                                     , timeout=self.timeout
                                     , headers=headers
                                     ).json()
        except Exception as e:
            logger.error("Failed to get x-guest-token => " + str(e))
            return

        self.GUEST_TOKEN = response["guest_token"]
        logger.info("Got x-guest-token: " + self.GUEST_TOKEN)

    def get_user_rest_id(self, screen_name):
        """
        Obtains the selected user's rest_id, needed to obtain its tweets

        Args:
            -> screen_name: The handler of the user (the one used to @mention the user)

        Returns:
            -> The numerical id, or None if the user didn't exist
        """
        logger = logging.getLogger(__name__ + ".get_user_rest_id")

        # If their info is already available in self.scraped_info, skips this step
        if screen_name in self.scraped_info:
            return self.scraped_info[screen_name]["rest_id"]

        try:
            response = requests.get(
                self.build_user_info_url(screen_name)
                , timeout=self.timeout
                , headers={
                    "Authorization": "Bearer " + self.BEARER_TOKEN,
                    "x-guest-token": self.GUEST_TOKEN
                }
            ).json()["data"]["user"]
        except Exception as e:
            logger.error("Failed to get user's REST id => " + str(e))
            return None

        rest_id = response["rest_id"]
        # Adds all the relevant information to the scraped_info object. Its structure can
        # be consulte
        self.scraped_info[screen_name] = {
            "id": response["id"]
            , "rest_id": rest_id
            , "tweets": []
            , "cursor": {"top": None, "bottom": None}
        }

        logger.info("Got ID of user " + screen_name + ": " + rest_id)
        return rest_id

    def get_next_page(username, max_position, full_html
                      , max_count=10, older_age=None):
        """
        Gets the tweets of the specified user from the update URL (to get new tweets from
        the infinite scrolling), up to 'max' elements; or until the max old date is reached
        (whatever comes first)

        Args:
            -> username: Name of the user whose tweets will be extracted, performing a
                request to https://twitter.com/<username>

            -> max_position: Parameter to perform the request

            -> full_html: BeautifulSoup object with the main HTML, to extract some global
                    data of the user, like the user's avatar

            -> max_count (optional): Maximum number of tweets to extract

            -> older_age (optional): Age of the oldest tweets to extract; in
                    UNIX epoch format

        Returns:
            -> A dictionary with the extracted tweets,
            or
            -> None, if the user hasn't been found
        """
        tweet_map = {}

        logger = logging.getLogger(__name__ + ".get_next_page")
        tweet_map = {}

        logger.info("Getting more tweets, starting from " + str(max_position))
        #    try:
        #        response = urllib2.urlopen (
        #                        build_newpage_url (username, max_position)
        #                        , timeout = timeout
        #                    ).read ()
        #
        #    except urllib2.HTTPError as e:
        #        logger.error ("No user found: '" + username + "' => " + str (e))
        #        return None
        #
        #    except urllib2.URLError as e:
        #        logger.error ("Timeout expired getting tweets of '" + username + "' => "
        #                        + str (e)
        #        )
        #        return None
        #
        #    except ssl.SSLError as e:
        #        logger.error ("Connection getting tweets of '" + username + "' => "
        #                        + str (e)
        #        )
        #        return None
        return None  # TODO: NOT IMPLEMENTED

        resp_map = json.JSONDecoder().decode(response)

        html = BeautifulSoup(resp_map["items_html"], "html.parser")

        # Deletes the old tweets on the page and adds the new ones
        container = full_html.select("#stream-items-id")[0]
        container.clear()
        container.append(html)

        html = str(full_html)

        print('test 2')
        # Gets the map with the tweets
        data = process_html(html, max_count, older_age)

        tweet_map = data["tweet_map"]
        n_items = len(data["tweet_map"])

        # Checks if the maximum amount of requested data has been extracted
        if n_items < max_count \
                and resp_map["has_more_items"] \
                and not data["older_age_reached"]:
            tweet_map.update(
                get_next_page(username
                              , resp_map["min_position"]
                              , full_html
                              , max_count - n_items
                              , older_age
                              )
            )

        return tweet_map

    def get_user_tweets(self, username, max_count=10, older_age=None):
        """
        Gets the tweets of the specified user, up to 'max' elements; or until the max old
        date is reached (whatever comes first)

        Args:
            -> username: Name of the user whose tweets will be extracted, performing a
                request to https://twitter.com/<username>

            -> max_count (optional): Maximum number of tweets to extract

            -> older_age (optional): Age of the oldest tweets to extract; in
                    UNIX epoch format

        Returns:
            -> A list with the extracted tweets, ordered from newest (index 0) to oldest
            or
            -> None, if the user hasn't been found
        """
        logger = logging.getLogger(__name__ + ".get_user_tweets")

        rest_id = self.get_user_rest_id(username)
        if not rest_id:
            logger.error("No user with name '" + username + "' has been found")
            return None

        try:
            # Doubles the timeout, as this information is crucial to get updates
            response = requests.get(
                self.build_twitter_url(rest_id, max_count)
                , timeout=(self.timeout * 2)
                , headers={
                    "Authorization": "Bearer " + self.BEARER_TOKEN,
                    "x-guest-token": self.GUEST_TOKEN
                }
            ).json()
        except KeyboardInterrupt as e:
            logger.error("Failed to get user's tweets => " + str(e))
            return None

        # There are two main objects:
        #    - $.globalObjects.tweets => Holds the tweets' info, without order
        #    - $.timeline.instructions[0].addEntries.entries => List to order the tweets
        elems = response["globalObjects"]["tweets"]
        tweets = {}

        try:
            pinned_entry = response["timeline"]["instructions"][1]["pinEntry"]["entry"] \
                ["content"]["item"]["content"]["tweet"]["id"]
        except Exception:
            logger.info("No pinned entry for user " + username)
            pinned_entry = None

        # Once again, the format for this JSON is available in the README.md
        for k in elems:
            user = self.scraped_info[username]

            # TODO: There has to be another endpoint to get more info about each tweet
            tweets[k] = {
                "tweet_id": k
                , "text": elems[k]["full_text"]
                , "retweet": elems[k]["full_text"][:2] == 'RT'
            }

        # Orders the tweets according to the timeline
        #    - $.timeline.instructions[0].addEntries.entries => List to order the tweets
        elems = response["timeline"]["instructions"][0]["addEntries"]["entries"]

        timeline = []
        for x in elems:
            content = x["content"]
            # Cursor
            if "operation" in content:
                cursor = content["operation"]["cursor"]
                # Updates the info in self.scraped_info
                if cursor["cursorType"] == "Top":
                    self.scraped_info[username]["cursor"]["top"] = cursor["value"]
                else:
                    self.scraped_info[username]["cursor"]["bottom"] = cursor["value"]

            # Tweet-id
            else:
                searched_id = content["item"]["content"]["tweet"]["id"]

                # Searches that tweet and appends it to the definitive list
                if searched_id in tweets:
                    # if the tweet is a retweet, skip
                    if tweets[searched_id]["retweet"]:
                        continue
                    timeline.append(tweets[searched_id])
                else:
                    # WTF?
                    logger.error("Tweet " + str(searched_id)
                                 + " expected in the timeline, but not found in the tweets list"
                                 )

        tmp = timeline + self.scraped_info[username]["tweets"]
        self.scraped_info[username]["tweets"] = tmp
        return timeline

    def get_tweets(self, users, max_count=10, older_age=None):
        """
        Gets the tweets of all the specified users, up to 'max' elements; or until the max
        old date is reached (whatever comes first)

        Args:
            -> users: A list with the name of the users whose tweets will be extracted,
                performing requests to https://twitter.com/<username>

            -> max_count (optional): Maximum number of tweets to extract

            -> older_age (optional): Age of the oldest tweets to extract; in
                    UNIX epoch format

        Returns:
            A dictionary with the extracted tweets.
        """
        #        tweets = {}
        logger = logging.getLogger(__name__ + ".get_tweets")

        for username in tqdm(users):

            logger.info("Getting tweets of '" + username + "'")
            print('Getting user tweets')
            data = self.get_user_tweets(username, max_count, older_age)

            if not data:
                #                tweets [username] = data
                #            else:
                logging.info("No data retrieved from '" + username + "'")

        return self.scraped_info


