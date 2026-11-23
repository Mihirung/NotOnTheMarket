# Planning, health and amenities

Three questions from the brief, and what was built to answer them:

1. Does a home's planning history (an application, an approval, a refusal)
   tell us it is about to be sold? Does the kind of job matter?
2. Can each home carry a signal for what could be built there, and what it
   would add in value, so people can search on it?
3. Do the search, the filters and the best-home finder use every signal we
   have, including air quality, health services, green and blue space and
   pubs (which some people want near and others want far)?

| What | Where from | Covers |
|---|---|---|
| Planning applications | UK PlanIt, which gathers council planning registers | A sample of council areas, 2003 to 2019 (see below) |
| Conservation areas, listed buildings, Article 4 directions, green belt, protected landscapes, National Parks, World Heritage Sites | planning.data.gov.uk (England), DataMapWales and Cadw (Wales) | Every address in England and Wales |
| The room behind and beside each house, its type and footprint | Ordnance Survey OpenMap Local building outlines, with each house's facing from the national run | Every house |
| Parks, playing fields, play space | OS Open Greenspace (166,448 sites, 356,527 entrances) | Every postcode |
| Woods, rivers, lakes, the sea | OS OpenMap Local | Every postcode |
| Pubs and bars, takeaways, restaurants and cafes | Food Standards Agency hygiene register (50,401 pubs and bars) | Every postcode |
| Air quality, GPs, hospitals, dentists, pharmacies | AHAH v4 inputs (already in the model) | Every postcode |

## 1. Planning applications and sales

**The data.** The government's national planning application dataset is
still empty, so the applications come from UK PlanIt, a free service run by
one person that gathers council planning registers. Its terms allow bulk
use overnight, one request a minute, about 300 requests a night, which is
roughly 20 council areas from 2003 to 2019 per night. A production version
would need a commercial planning feed; PlanIt's owner asks that no
commercial service be built on it.

**Joining applications to homes.** The sale records identify a home by its
postcode, house number or name, and flat. The same key is built from each
application's address, so an application lands on the exact home whose
sales we know, not just its postcode.

**The job.** Each application's description is read for the kind of work:
loft or dormer, two-storey extension, single-storey rear extension, side
extension, wrap-around, basement, garage conversion, garden building,
porch, a new home, splitting into flats, listed building consent, a
certificate of lawful development, windows and doors, walls and drives,
trees, change of use, demolition.

**What was fetched.** 430,320 applications from 14 council areas: Bath,
Brighton, Bristol, Cambridge, Canterbury, Cheltenham, Exeter, Guildford,
Norwich, Plymouth, Reading, Stockport, Trafford and York, 2003 to 2019. 48%
landed on a home with a sale record. 85% of decided applications were
approved.

**Does planning activity come before a sale?** Mostly it comes after one. The
year a home's first application goes in, and the year before it, are the
years it is most likely to have just sold: about twice the usual rate. New
owners apply soon after they buy. Looking only at what is known before the
year in question, which is all a forecast can use:

| What happened at the home | Chance of selling this year, against similar homes in the same area |
|---|---|
| An application approved last year | 0.77 times (23% less likely) |
| An application approved two or three years ago | 0.79 times |
| An approval longer ago, 4 to 6 years | 0.92 to 0.93 times |
| An application refused two or three years ago | 1.05 times |
| An application withdrawn last year | 1.20 times (range 1.10 to 1.30) |
| An application still undecided | 0.94 times |

People who win permission stay and build. People who withdraw an
application are more likely to move instead.

**The kind of job.** Approved in the three years before:

| Job | Chance of selling, against similar homes |
|---|---|
| Side extension | 0.70 times |
| Single-storey rear extension | 0.75 times |
| Two-storey extension | 0.77 times |
| Garden building | 0.80 times |
| Loft or dormer | 0.90 times |
| Windows, doors, walls, drives, trees | about 1 (no difference) |
| A new home on the plot | 1.47 times |
| Commercial use | 0.47 times |

**What the description says about the home.** Applications often name the
house: "bungalow", "Victorian", "barn conversion", "listed building". Homes
called bungalows sell 1.25 times as often as similar homes (older owners),
and homes whose applications mention a listing 1.15 times. Era words
(Georgian, Victorian, Edwardian) are too rare in this sample to measure
clearly.

**Does it make the model better?** No. Added to the deployed national model
in these 14 areas and judged on 2015 to 2019, the planning history changes
the sellers found in the best tenth of each district by -0.003 (range -0.013
to +0.007). The model already knows how long each owner has been there and
what could be built at the house, which carry most of what planning history
says. It stays out of the model; it is kept for the record of each home.

**Will it be approved?** A model of approval from the kind of job, the
designations at the house and the council area separates approvals from
refusals with a cross-validated AUC of 0.705. Rear and side extensions are
approved 91% of the time, lofts 82%, two-storey extensions 81%, splitting a
house into flats 73% and new homes 64%. In conservation areas approval
rates for most jobs are the same or slightly higher, because applicants
there already work to the rules.

**What a job adds to the price.** Homes sold before and after an approved
job, against homes in the same sector sold in the same two years without
one:

| Job | Extra price growth between the two sales | 95% range | Homes |
|---|---|---|---|
| Two-storey extension | +19.0% | +17.9% to +20.1% | 4,537 |
| Loft or dormer | +15.6% | +14.7% to +16.6% | 2,574 |
| Extension, unspecified | +12.1% | +8.7% to +14.4% | 431 |
| Side extension | +11.6% | +10.2% to +12.9% | 880 |
| Basement | +10.2% | +5.7% to +15.0% | 196 |
| Single-storey rear extension | +9.7% | +9.3% to +10.3% | 6,204 |
| Garden building | +8.1% | +6.9% to +9.5% | 935 |
| Garage | +2.0% | -0.4% to +5.0% | 233 |

Neighbours without an application grew at the sector's rate (+0.0%), as
they should.

## 2. What could be built at each house, and what it would add

**Where it stands.** Every one of the 28.1 million address positions in
England and Wales is tagged with the designations that limit building:
conservation area, listed building (a whole terrace listed as one entry
reaches every house in it), Article 4 directions sorted by the rights they
remove (using the national codes: house extensions, roof alterations,
houses in multiple occupation), green belt, protected landscape, National
Park and World Heritage Site.

**The room around it.** From the building outlines and the way each house
faces, every house gets the open ground behind it to the next building, the
gap at each side, and its own share of the outline it stands on. A house
alone on its outline is detached; two addresses on one outline are a pair
of semis; three or more are a terrace.

**The rules.** Householder permitted development lets the owner of a house
(not a flat) extend within limits without applying: a single-storey rear
extension of 3 m (4 m detached), or 6 m (8 m) after a prior-approval notice
in England; a two-storey rear extension of 3 m at least 7 m from the rear
boundary; a side extension up to half the house's width; a loft adding
40 m3 (terraced) or 50 m3 of roof; garden buildings. Listed buildings have
none of this. Conservation areas, protected landscapes, National Parks and
World Heritage Sites rule out side, two-storey and roof extensions and the
larger rear extensions; Article 4 directions remove what they name.

**The value.** The floor space the rules allow is multiplied by the
postcode's price per square metre (its typical house value over its houses'
typical floor area, from the outlines and storeys) and by 0.7, the share of
the average price per square metre that extra space usually fetches. That
factor is an assumption until the planning sample measures it (section 1).

**What it found.** Of the houses in England and Wales:

| What could be done without applying | Share of houses |
|---|---|
| A single-storey rear extension | 90.0% |
| A loft extension | 86.9% |
| Nothing at all (listed, or no room) | 4.2% |

The single largest job allowed is a rear extension for 48.8% of houses, a
loft for 30.0%, a side extension for 10.7% and a two-storey extension for
6.2%. It adds a median of 30 m2, about 19% of the house's value, or
£43,000 at 2019 prices; every allowance together would add 62 m2. Of all
address positions, 9.1% are in a conservation area, 3.3% are listed, 2.3%
are in the green belt, 2.5% in a protected landscape, 0.85% in a National
Park and 0.48% in a World Heritage Site.

**Against what jobs are measured to add** (section 1): 10% for a rear
extension, 16% for a loft, 19% for two storeys. The estimate for the largest
job allowed sits at the top of that range, so the 0.7 factor is probably
generous. It will be set from these measurements once the size of each
extension is read from its application.

**In the model.** What could be built is worth more to the sale-timing model
than any other new family: +0.037 sellers found per district best tenth
(range +0.020 to +0.053). It is in the deployed model
([08](08-every-house-in-england-and-wales.md)).

These are estimates for search and conversation, not advice: allowances are
measured from the original house, so earlier extensions use them up, and
boundaries, design and neighbours matter.

## 3. Every signal in the search

Every signal is now in the search, the filters and the best-home finder.

| Signal | Search page | Best-home finder | Each house's page | Sale-timing model |
|---|---|---|---|---|
| Air quality | slider | clean air | yes | yes |
| GP, hospital | sliders | near a GP, near a hospital | yes | yes |
| Parks, parkland, woods | park slider | near a park, parkland, near woods | yes | tested: no gain |
| Rivers, lakes, the sea | water slider | near water, near the coast | yes | tested: no gain |
| Pubs | near, far or don't mind | pubs near or pubs far | yes | tested: no gain |
| Restaurants, takeaways | | restaurants, few takeaways | yes | tested: no gain |
| What could be built | could-add tag, build chips | extension value and space, loft | yes | yes |
| Climate ([08](08-every-house-in-england-and-wales.md)) | climate choices | 14 climate choices | yes | being tested |

Green and blue space and pubs carry a price (all 11 columns have a premium
clear of zero) but do not help the model find sellers (+0.005, range -0.010
to +0.020), and adding them to the deployed set makes it slightly worse. So
they serve buyers, not the forecast.

## Limits

- Planning applications cover 14 council areas so far, not the country; more
  are fetched each night within PlanIt's limits.
- Property boundaries are not in open data: garden depth is estimated from
  the gap to the next building behind.
- Some Article 4 directions do not state which rights they remove; they are
  flagged for checking rather than assumed.
- Distances are straight lines, not walking routes.
