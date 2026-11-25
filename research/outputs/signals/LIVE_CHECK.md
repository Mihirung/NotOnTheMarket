# The model on current sales: any day of the year, and years on

Sale records to 2026-09 (live_sales.py). Homes: the tenth never used to fit the lab's model. Each cell scores the homes owned on the first of that
month and counts the sellers of the twelve months that follow, found in the best tenth of each postcode district, times
random. A star marks a day whose twelve months run into the last six on record, which are only part registered: fewer
sales are counted, in the best tenth and outside it alike.

## The model fitted on sales to 2015

| Scored on the first of | January | April | July | October |
|---|---|---|---|---|
| 2017 | 1.734 | 1.727 | 1.750 | 1.734 |
| 2018 | 1.748 | 1.738 | 1.711 | 1.711 |
| 2019 | 1.704 | 1.703 | 1.703 | 1.691 |
| 2020 | 1.681 | 1.664 | 1.627 | 1.674 |
| 2021 | 1.657 | 1.729 | 1.806 | 1.794 |
| 2022 | 1.804 | 1.793 | 1.758 | 1.755 |
| 2023 | 1.739 | 1.707 | 1.691 | 1.678 |
| 2024 | 1.663 | 1.645 | 1.694 | 1.688 |
| 2025 | 1.693 | 1.702 | 1.688* | 1.717* |

## The deployed model, fitted on sales to 2018

| Scored on the first of | January | April | July | October |
|---|---|---|---|---|
| 2019 | 1.771 | 1.770 | 1.749 | 1.727 |
| 2020 | 1.709 | 1.711 | 1.668 | 1.700 |
| 2021 | 1.720 | 1.781 | 1.829 | 1.829 |
| 2022 | 1.828 | 1.810 | 1.768 | 1.767 |
| 2023 | 1.738 | 1.717 | 1.711 | 1.706 |
| 2024 | 1.701 | 1.672 | 1.731 | 1.717 |
| 2025 | 1.725 | 1.745 | 1.733* | 1.764* |

## Sales not yet registered

The latest file holds 100%, 84%, 68%, 71%, 57%, 27% of the sales of its last six
months, oldest first, judged against the same months a year before. 2025-10-01 is scored again with that share of its own last six
months hidden (131,552 sales), by the deployed model.

| | Best tenth, times random |
|---|---|
| Every sale before the day known | 1.764 (1.729 to 1.798) |
| Part of the last six months hidden | 1.700 (1.665 to 1.732) |
| The same, each sale of a part-registered month counted for those still to come | 1.748 (1.713 to 1.781) |
| The same, among homes that had not just been sold | 1.706 (1.669 to 1.736) |

Homes sold in those six months whose sale was hidden are 0.6% of the homes scored and 1.0% of the best tenth
(1.7 times random): the ranking finds them because they were about to sell, and cannot know they have.
