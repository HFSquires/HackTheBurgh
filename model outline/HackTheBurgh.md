The model is as follows:
Each month $n$, one gets their salary $s_{n}$ and others income $i_{n}$ (from investments etc.), and spends their money: either through regular payments (mortgage, subscriptions etc.) $\mathrm{reg}_{n}$ or "random" spendings $\mathrm{rand}_{n}$ that can be categorised into various categories (groceries, going out etc.). Given granular data (purchase-by-purchase) from the last few months, the model infers the monthly salary $s_{n}$ and other income $i_{n}$. It also infers the regular payments. Finally, it makes a prediction on the next month's random spending by taking the average random spending from the last $k$ months and multiplying it by a weight $w_{n}$ that corresponds to how much each month contributes to the yearly spending.

# Calculating weights
Use aggregated data from various bank statements to calculate the weights $w_{n}=\frac{\text{total money spent in month }n}{\text{total money spent across the year}}$. Make sure to split people into categories (living alone, have dependants, living with a partner, age etc.) to get more relevant results. Then apply the right category for the person in question.

# Predicting monthly movement
The prediction of the random spending in a given month is the average random spending from the last $k$ months multiplied by the corresponding (calculated as explained above) weight. This gives a prediction $\hat{r}_{n}$. If we are $d$ days into the month of length $D$ days, then the prediction of what is left to spent till the end of the month is $\frac{D-d}{D}\hat{r}_{n}$. 

# Total balance
Take user's bank statements and calculate the trend of end-of-the-month balance. The goal is to increase net worth in order to be able to make savings, invest (thus increasing $i_{n}$) etc. The user can choose the goal rate at which their net worth increases, with the bare minimum being "beats inflation".

# Decision making
At the end of the checkout, the program looks at how the potential spending will impact the monthly movement (i.e. calculates $\hat{r}_{n}$ and adds the cost to it). There are four options:
1. User still meets their selected goal -- they see the message that they can buy the item. The message is color-coded, with green being that they are way above their goal and orange being that they cannot afford the item if they want to meet their goal
2. User doesn't meet their goal: the red message says that it will set them back too much
3. User doesn't meet their BUT they could instead put that spending into their ISA or some other investments -- thus increasing their monthly income but keeping their net worth the same. Then the message is blue and says in how many days the user will be able to afford the item.
4. Rainbow message: a cheaper option was found somewhere else online. It fits either the "afford" or "invest" scenarios.