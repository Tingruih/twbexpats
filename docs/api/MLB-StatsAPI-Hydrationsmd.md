## Hydrations

Standard API calls return a predefined, fixed set of information. However, frequently a consumer may wish to combine information from multiple API endpoints. This is achieved through separate API calls but, in some cases, the user may find it advantageous to utilize hydrations as a way of supplementing an API call with additional information without requiring a separate API request. In the Stats API, a  $ \underline{\text{Game-hydration}} $ is the concept of supplementing an API call with additional information without requiring a separate API request.

For example, here is the Schedule endpoint as an example: https://statsapi.mlb.com/api/v1/schedule/?sportId=1&date=06/17/2018&hydrate=team

To add further detail, multiple hydrations may be requested simultaneously. Hydrations are passed in as a comma delimited list parameter to hydrate. Adding one hydrate returns an expanded set of desired data. Subsequent hydrates add on further sets, adjacent to the first. This achieves great flexibility and efficiency when creating the requests to include large amounts of information within a single call.

The following is a request of a base Schedule response but with additional information from the Team and probablePitcher hydrations as well: https://statsapi.mlb.com/api/v1/schedule/?sportId=1&date=06/17/2018&hydrate=team,probablePitcher. Along with the base Team call, any hydrations that are available in the Team endpoint will now be available by using parentheses to denote a nested hydration within the parent. For example, https://statsapi.mlb.com/api/v1/schedule/?sportId=1&date=06/17/2018&hydrate=team(league,standings),probablePitcher hydrates League and Standings data (notice the comma separation within the parentheses) associated with the Teams hydration.

Another example is the Roster endpoint. This endpoint returns Person objects by default but we can go further and hydrate the players' education information by nesting the hydrations as follows:

Nesting One - http://statsapi.mlb.com/api/v1/teams/120/roster/active?hydrate=person(education)

Nesting Multiple - http://statsapi.mlb.com/api/v1/teams/120/roster/active?hydrate=person(education,draft)

As shown, hydrations are very powerful mechanisms for tying various related data sets into a single call, and can be chained together to produce deep and complex responses. It should be noted that as more hydrations are requested, the responses can become quite large and perhaps cumbersome to parse. Some hydrations require parameters to be supplied in order to function. For example, stats hydrations are cases that often require extra parameters:

For example,http://statsapi.mlb.com/api/v1/teams/111/roster?
rosterType=active&hydrate=person(stats(group=[hitting,pitching],type=season,season=2016))

This call returns all the players in the active roster for Red Sox and also hydrates their 2016 season hitting and pitching stats. In some cases, default parameters can be inferred when certain hydration parameters are not defined by the user. In this example, the current season is used if no season was specified. Likewise, the group (hitting, pitching, fielding) most relevant to the player's position is used if none are listed.

#### ⑦ NOTE

When the value of a hydration parameter like group is a list, it must be comma-separated and wrapped in square brackets. (e.g. group=[hitting,pitching])

In order to view the supported hydrates for each endpoint, add hydrate=hydrations. For example, http://statsapi.mlb.com/api/v1/people/592450?hydrate=hydrations returns each available hydration for the people endpoint regardless of the player. For further information about the endpoints of API calls, please consult the relevant Configs section to confirm each endpoint available.

Hydrations are currently available for the following endpoints:

#### People

View Hydrations

articles

awards

• currentTeam

• draft

education

mixedFeed

• relatives

• rookieSeasons

rosterEntries

• social

stats

• team

• transactions

videos

xref

##### Stats

View Hydrations

person

• team

#### Schedule

View Hydrations

broadcasts

broadcasts(all)

• decisions

event(designations)

event(performers)

event(game)

event(promotions)

event(status)

event(tickets)

event(venue)

event(timezone)

game(atBatPromotions)

• game(content(all))

• game(atBatTickets)

• game(content(editorial(all)))

• game(content(editorial(articles)))

• game(content(editorial(preview)))

• game(content(editorial(recap)))

• game(content(editorial(wrap)))

• game(content(gamenotes))

• game(content(highlights(all)))

• game(content(highlights(gamecenter)))

• game(content(highlights(highlights)))

• game(content(highlights(live)))

• game(content(highlights(milestone)))

• game(content(highlights(scoreboard)))

• game(content(highlights(scoreboardPreview)))

• game(content(media(all)))

• game(content(media(epg)))

• game(content(media(featured)))

• game(content(media(milestones)))

• game(content(summary))

• game(content)

• game(promotions)

• game(seriesSummary)

• game(sponsorships)

• game(tickets)

linescore

linescore(matchup)

linescore(runners)

linescore(defense)

• metadata

• officials

• probablePitcher

• radioBroadcasts

• scoringplays

seriesStatus

• team

tickets

• venue

weather

weatherForecast

### Standings

View Hydrations

• conference

• division

• league

• record(conference)

• record(division)

• sport

• team

#### Teams

View Hydrations

deviceProperties

• division

• game(atBatPromotions)

• game(atBatTickets)

• game(promotions)

• game(promotions)

• game(sponsorships)

• game(tickets)

• league

• nextSchedule

person

previousSchedule

• social

• sport

• springVenue

standings

• venue

videos

• xrefld

#### Venue

View Hydrations

• images

• location

• menu

• metadata

• nextSchedule

parentVenues

parentVenues(venue)

performers

previousSchedule

relatedApplications

relatedVenues

relatedVenues(venue)

• residentVenues

• residentVenues(venue)

• schedule

• social

ticketManagement

• timezone

• xref

