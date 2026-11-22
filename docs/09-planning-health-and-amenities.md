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

PLANNING_RESULTS

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

PD_RESULTS

These are estimates for search and conversation, not advice: allowances are
measured from the original house, so earlier extensions use them up, and
boundaries, design and neighbours matter.

## 3. Every signal in the search

AMENITY_RESULTS

## Limits

- Planning applications cover a sample of council areas, not the country.
- Property boundaries are not in open data: garden depth is estimated from
  the gap to the next building behind.
- Some Article 4 directions do not state which rights they remove; they are
  flagged for checking rather than assumed.
- Distances are straight lines, not walking routes.
