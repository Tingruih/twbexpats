## Hydrations（資料擴充）

標準的 API 呼叫會回傳一組預先定義、固定的資訊。然而，使用者經常會希望將多個 API 端點的資訊組合在一起。這可以透過個別的 API 呼叫來達成，但在某些情況下，使用者可能會發現利用 hydrations 來補充 API 呼叫的額外資訊，而不需要另外發出一次 API 請求，會更為有利。在 Stats API 中，$ \underline{\text{Game-hydration}} $ 是指在不需要另外發出 API 請求的情況下，為 API 呼叫補充額外資訊的概念。

舉例來說，以下是 Schedule 端點的範例：https://statsapi.mlb.com/api/v1/schedule/?sportId=1&date=06/17/2018&hydrate=team

若要加入更多細節，可以同時要求多個 hydrations。Hydrations 是以逗號分隔的清單參數傳入 hydrate 參數中。加入一個 hydrate 會回傳一組擴充後的所需資料。之後加入的 hydrate 會在第一組資料旁再附加更多資料集。這在建立單一呼叫即可包含大量資訊的請求時，能達到極高的彈性與效率。

以下是一個基礎 Schedule 回應的請求範例，但額外加入了來自 Team 與 probablePitcher hydrations 的資訊：https://statsapi.mlb.com/api/v1/schedule/?sportId=1&date=06/17/2018&hydrate=team,probablePitcher。除了基本的 Team 呼叫之外，任何 Team 端點中可用的 hydrations，現在都可以透過括號來標示為父層 hydration 之下的巢狀 hydration 而使用。舉例來說，https://statsapi.mlb.com/api/v1/schedule/?sportId=1&date=06/17/2018&hydrate=team(league,standings),probablePitcher 會擴充與 Teams hydration 相關聯的 League 與 Standings 資料（注意括號內以逗號分隔）。

另一個範例是 Roster 端點。此端點預設會回傳 Person 物件，但我們可以更進一步，透過以下方式巢狀化 hydrations，來擴充球員的教育資訊：

單層巢狀 - http://statsapi.mlb.com/api/v1/teams/120/roster/active?hydrate=person(education)

多層巢狀 - http://statsapi.mlb.com/api/v1/teams/120/roster/active?hydrate=person(education,draft)

如上所示，hydrations 是將各種相關資料集串連至單一呼叫的強大機制，並可以串接在一起，產生深且複雜的回應。需要注意的是，隨著要求的 hydrations 越多，回應也可能變得相當龐大，解析上或許會較為繁瑣。有些 hydrations 需要提供參數才能運作。舉例來說，stats hydrations 就經常需要額外的參數：

舉例來說，http://statsapi.mlb.com/api/v1/teams/111/roster?
rosterType=active&hydrate=person(stats(group=[hitting,pitching],type=season,season=2016))

此呼叫會回傳紅襪隊現役名單（active roster）中的所有球員，並同時擴充他們 2016 年球季的打擊與投手數據。在某些情況下，若使用者未定義特定的 hydration 參數，系統可以推斷出預設參數。在此範例中，若未指定球季，則會使用目前球季。同樣地，若未列出 group（打擊、投手、守備），則會使用與該球員位置最相關的 group。

#### ⑦ 注意事項

當 hydration 參數（例如 group）的值為一份清單時，必須以逗號分隔並以中括號包住。（例如 group=[hitting,pitching]）

若要查看每個端點所支援的 hydrates，可加入 hydrate=hydrations。舉例來說，http://statsapi.mlb.com/api/v1/people/592450?hydrate=hydrations 會回傳 people 端點可用的每一個 hydration，無論該球員為何。關於 API 呼叫端點的進一步資訊，請參閱相關的 Configs 章節，以確認每個可用的端點。

目前下列端點皆支援 Hydrations：

#### People（人員）

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

##### Stats（數據）

View Hydrations

person

• team

#### Schedule（賽程）

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

### Standings（排名）

View Hydrations

• conference

• division

• league

• record(conference)

• record(division)

• sport

• team

#### Teams（球隊）

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

#### Venue（球場）

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
