import scraper

if __name__ == '__main__':
    s = scraper.Scraper()
    data = s.get_tweets(["realDonaldTrump"], max_count=100)
    print(data)

