# Homes named in a notice that the sale records do not hold

The model scores only homes with a sale on record since 1995. These are the others: homes named in a notice with no
sale on record when the year began, 2017 and 2018 together. Homes that do have a record sell at 4.0% a year.
The product counts in a kind of notice only where the whole range is above that, and then only the homes its model
scores above that.

## Bankruptcy order

127,323 notices with an address; 56% name a home with no sale on record at all. 116 at care or nursing homes are left out. Measured on 60,914 home-years.

| Homes | Number | First sold in the year (95% range) | Completes July to June |
|---|---|---|---|
| All | 60,914 | 1.4% (1.3 to 1.5) | 1.4% |
| 1 to 6 months before | 6,963 | 1.1% (0.9 to 1.4) | 1.2% |
| 7 to 12 months before | 6,842 | 1.3% (1.1 to 1.6) | 1.3% |
| 13 to 24 months before | 13,776 | 1.5% (1.3 to 1.7) | 1.7% |
| 25 to 36 months before | 15,324 | 1.5% (1.3 to 1.7) | 1.5% |
| 37 to 48 months before | 18,009 | 1.4% (1.2 to 1.6) | 1.4% |
| A flat or a named block | 8,952 | 0.5% (0.4 to 0.7) | 0.5% |
| Any other address | 51,962 | 1.6% (1.5 to 1.7) | 1.6% |

Not counted in: these homes do not clearly sell more often than a home on record (4.0% a year), or there are too few to tell.

## Deceased-estate notice

208,583 notices with an address; 55% name a home with no sale on record at all. 25,212 at care or nursing homes are left out. Measured on 82,806 home-years.

| Homes | Number | First sold in the year (95% range) | Completes July to June |
|---|---|---|---|
| All | 82,806 | 11.2% (11.0 to 11.4) | 5.9% |
| 1 to 6 months before | 15,273 | 30.3% (29.6 to 31.1) | 13.4% |
| 7 to 12 months before | 12,882 | 17.2% (16.6 to 17.8) | 7.7% |
| 13 to 24 months before | 20,255 | 6.9% (6.6 to 7.2) | 4.4% |
| 25 to 36 months before | 18,343 | 3.4% (3.1 to 3.6) | 2.8% |
| 37 to 48 months before | 16,053 | 2.6% (2.4 to 2.9) | 2.5% |
| A flat or a named block | 16,517 | 2.2% (2.0 to 2.4) | 1.3% |
| Any other address | 66,289 | 13.5% (13.2 to 13.7) | 7.0% |

The model against one rate per band of months, each home scored by a model that never saw it or its year: log loss 0.30227 with bands, 0.27736 with the model, a change of -0.02490 (-0.02633 to -0.02348). The model expected 9,287 first sales; there were 9,286.

| Fifth of homes, by the model's score | Homes | Model expected | Sold in the year |
|---|---|---|---|
| Lowest | 16,562 | 1.3% | 1.0% |
| Second | 16,561 | 3.1% | 3.1% |
| Middle | 16,561 | 5.1% | 5.5% |
| Fourth | 16,561 | 11.6% | 11.7% |
| Highest | 16,561 | 35.0% | 34.8% |

What the product's model leans on, by share of its gain: months 64%, flat 16%, on_record 10%, age_85_plus 2%, flats 2%, own_outright 1%.

Set against 2019, a year the model never saw: it counts in 27,523 of 45,814 homes and expected 4,951 first sales; there were 4,412 (16.0%). The 18,291 homes it leaves out sold at 1.9%.

Lower bounds: an address that fails to match its later sale record counts as not sold.
