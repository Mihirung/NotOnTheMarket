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

## Homes not yet on the market

Scored on 1 January; the sellers counted are those completing between July of that year and June of the next. A model
is shown only for the years after the last one it was fitted on.

| Scored on 1 January | Later sales with certificates, fitted to 2015 | Later sales with certificates, fitted to 2018 (the site's) | Next twelve months, fitted to 2015 | Next twelve months, fitted to 2018 (the model before) |
|---|---|---|---|---|
| 2019 | 1.747 | 1.748 | 1.628 | 1.701 |
| 2020 | 1.685 | 1.732 | 1.597 | 1.623 |
| 2021 | 1.613 | 1.637 | 1.648 | 1.681 |
| 2022 | 1.687 | 1.782 | 1.719 | 1.740 |
| 2023 | 1.777 | 1.788 | 1.696 | 1.697 |
| 2024 | 1.750 | 1.745 | 1.671 | 1.698 |
| 2025 | 1.793* | 1.803* | 1.641* | 1.684* |

2024-10-01 with part of its last six months hidden and counted up, as the live site scores (131,141 sales hidden; the homes just sold are 0.5% of those scored):

| Model | Every sale known | Part hidden, counted up | Just sold, share of the best tenth |
|---|---|---|---|
| Next twelve months, fitted to 2015 | 1.653 (1.625 to 1.685) | 1.634 (1.602 to 1.664) | 0.9% |
| Later sales with certificates, fitted to 2015 | 1.767 (1.735 to 1.797) | 1.740 (1.709 to 1.769) | 1.3% |
| Next twelve months, fitted to 2018 (the model before) | 1.692 (1.661 to 1.721) | 1.665 (1.636 to 1.694) | 1.0% |
| Later sales with certificates, fitted to 2018 (the site's) | 1.736 (1.704 to 1.768) | 1.711 (1.681 to 1.743) | 1.4% |
