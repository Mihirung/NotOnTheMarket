# Homes named in a notice that the sale records do not hold

The model scores only homes with a sale on record since 1995. These are the others: homes named in a notice with no
sale on record when the year began, 2017 and 2018 together. Homes that do have a record sell at 4.0% a year.
The product counts in a kind of notice only where the whole range is above that, and then only the homes its model
scores above that.

## Bankruptcy order

123,900 notices with an address; 56% name a home with no sale on record at all. 116 at care or nursing homes are left out. Measured on 60,914 home-years.

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

93,276 notices with an address; 52% name a home with no sale on record at all. 11,359 at care or nursing homes are left out. Measured on 57,999 home-years.

| Homes | Number | First sold in the year (95% range) | Completes July to June |
|---|---|---|---|
| All | 57,999 | 14.8% (14.5 to 15.0) | 7.3% |
| 1 to 6 months before | 15,273 | 30.3% (29.6 to 31.1) | 13.4% |
| 7 to 12 months before | 12,882 | 17.2% (16.6 to 17.8) | 7.7% |
| 13 to 24 months before | 20,255 | 6.9% (6.6 to 7.2) | 4.4% |
| 25 to 36 months before | 9,589 | 3.2% (2.9 to 3.6) | 2.9% |
| A flat or a named block | 11,094 | 2.9% (2.6 to 3.2) | 1.6% |
| Any other address | 46,905 | 17.6% (17.2 to 17.9) | 8.6% |

The model against one rate per band of months, each home scored by a model that never saw it or its year: log loss 0.39042 with bands, 0.34357 with the model, a change of -0.04685 (-0.04881 to -0.04473). The model expected 8,700 first sales; there were 8,556.

| Fifth of homes, by the model's score | Homes | Model expected | Sold in the year |
|---|---|---|---|
| Lowest | 11,600 | 2.5% | 1.8% |
| Second | 11,600 | 5.3% | 5.0% |
| Middle | 11,599 | 8.8% | 8.3% |
| Fourth | 11,600 | 18.9% | 19.5% |
| Highest | 11,600 | 39.5% | 39.2% |

What the product's model leans on, by share of its gain: months 55%, flat 20%, on_record 12%, age_85_plus 3%, flats 2%, own_outright 2%.

Lower bounds: an address that fails to match its later sale record counts as not sold.
