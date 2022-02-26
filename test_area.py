import pandas as pd

df_1 = pd.DataFrame([{"order": "abc"}, {"order": "xyz"}])

df_1["attributes"] = [{"att1": 1, "att2": 2, "att3": 3, "att4": 4},]

df_1 = df_1.join(pd.DataFrame(df_1.pop("attributes").values.tolist()))
print(df_1)