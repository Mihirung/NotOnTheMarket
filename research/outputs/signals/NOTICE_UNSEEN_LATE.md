# Homes named in a notice that the sale records do not hold

The model scores only homes with a sale on record since 1995. These are the others: homes named in a notice with no
sale on record when the year began, 2017 and 2018 together. Homes that do have a record complete a sale between July and the next June at 3.9%.
The product counts in a kind of notice only where the whole range is above that, and then only the homes its model
scores above that.

## Bankruptcy order

154,239 notices with an address; 55% name a home with no sale on record at all. 125 at care or nursing homes are left out. Measured on 60,914 home-years.

| Homes | Number | Completes July to June (95% range) | First sold in the year |
|---|---|---|---|
| All | 60,914 | 1.4% (1.4 to 1.5) | 1.4% |
| 1 to 6 months before | 6,963 | 1.2% (1.0 to 1.5) | 1.1% |
| 7 to 12 months before | 6,842 | 1.3% (1.1 to 1.6) | 1.3% |
| 13 to 24 months before | 13,776 | 1.7% (1.4 to 1.9) | 1.5% |
| 25 to 36 months before | 15,324 | 1.5% (1.3 to 1.7) | 1.5% |
| 37 to 48 months before | 18,009 | 1.4% (1.2 to 1.6) | 1.4% |
| A flat or a named block | 8,952 | 0.5% (0.4 to 0.7) | 0.5% |
| Any other address | 51,962 | 1.6% (1.5 to 1.7) | 1.6% |

Not counted in: these homes do not clearly sell more often than a home on record (3.9% a year), or there are too few to tell.

## Deceased-estate notice

292,587 notices with an address; 60% name a home with no sale on record at all. 33,184 at care or nursing homes are left out. Measured on 82,806 home-years.

| Homes | Number | Completes July to June (95% range) | First sold in the year |
|---|---|---|---|
| All | 82,806 | 5.9% (5.7 to 6.0) | 11.2% |
| 1 to 6 months before | 15,273 | 13.4% (12.9 to 14.0) | 30.3% |
| 7 to 12 months before | 12,882 | 7.7% (7.2 to 8.2) | 17.2% |
| 13 to 24 months before | 20,255 | 4.4% (4.2 to 4.7) | 6.9% |
| 25 to 36 months before | 18,343 | 2.8% (2.6 to 3.1) | 3.4% |
| 37 to 48 months before | 16,053 | 2.5% (2.3 to 2.7) | 2.6% |
| A flat or a named block | 16,517 | 1.3% (1.1 to 1.5) | 2.2% |
| Any other address | 66,289 | 7.0% (6.8 to 7.2) | 13.5% |

The model against one rate per band of months, each home scored by a model that never saw it or its year: log loss 0.21059 with bands, 0.20044 with the model, a change of -0.01015 (-0.01109 to -0.00927). The model expected 4,850 first sales; there were 4,861.

| Fifth of homes, by the model's score | Homes | Model expected | Completes July to June |
|---|---|---|---|
| Lowest | 16,562 | 1.1% | 0.7% |
| Second | 16,561 | 2.5% | 2.5% |
| Middle | 16,561 | 4.0% | 4.4% |
| Fourth | 16,561 | 6.6% | 6.9% |
| Highest | 16,561 | 15.2% | 14.8% |

What the product's model leans on, by share of its gain: months 50%, flat 20%, on_record 13%, age_85_plus 4%, own_outright 3%, flats 2%.

Lower bounds: an address that fails to match its later sale record counts as not sold.
