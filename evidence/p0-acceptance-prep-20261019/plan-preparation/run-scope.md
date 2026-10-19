# Acceptance plan review scope

Prepared and validated only. No execution authorization was generated.

Run order 1–8 covers all eight distinct cases; review actual results before repeats. Run serially.

| Order | Case | Point | Method | Repeat | Plan SHA256 |
|---:|---|---|---|---:|---|
| 1 | E1-a | after_observation | — | 1 | d2608812aaa9495b6195a431a801aeafa4f74574d0fd338f846f00bf83746a60 |
| 2 | E1-a | before_modification | — | 1 | 9af07a2ca78d8bf0cf2b07871633d2ef7dd1db11577e2ee21a44c11718136463 |
| 3 | E1-a | after_applied | — | 1 | 456ea7f174040bcc8cb77aac091e8ace9f18916c97ec8127dc94ba2086a0d4cf |
| 4 | E1-b | after_applied | from_scratch | 1 | 581ef866a84c051f81df1751628f701035ad946895dd846dec6b611c5224bb43 |
| 5 | E1-b | after_applied | full_history | 1 | 8464ca360a820de1caa3a872edd7cbf0b10694faf2b956b0275aa6f9ee3987bd |
| 6 | E1-b | after_applied | resume_package | 1 | 86ba8f8f5044e1ec288d4e3d26f26a83cf1b088c03610d233dfbe93d2bb84dd9 |
| 7 | E1-c | before_modification | — | 1 | d78ba3e03c620d0c94b88e37406efe98cd3f5657da26101cc449b2391f7bae5e |
| 8 | F12/E5 | — | — | 1 | 8e2e3e509c87cc21dc6742a66689d985bdc558c0f770528d6c0efe71dc3cd3aa |
| 9 | E1-a | after_observation | — | 2 | 9591feb547024d43f2f8f28a6bafe6a4dddc3769a4955329b625affd0ec4ccb4 |
| 10 | E1-a | before_modification | — | 2 | 12f5ce1a525780722fc0031f8f6c72b4cd023fc6c6a73c030e10109fe67ea5fc |
| 11 | E1-a | after_applied | — | 2 | 1ff2f2747cd5d0791038bae68ba189b41ed08ee73d53da0bdd22876b5d565f1f |
| 12 | E1-b | after_applied | from_scratch | 2 | 2f0e9710e2adeee1b01ea5a8972e771693c15f79e0d171e654ee63824a3a9295 |
| 13 | E1-b | after_applied | full_history | 2 | 7efec6153d00d844f0ea92fdb3a7f76decc7730a2fd70cedb96dd408d7d930d7 |
| 14 | E1-b | after_applied | resume_package | 2 | 74dc015453474fc01bb7f689052f849d392de25b2d655cda2c8ea2d9cc4147fd |
| 15 | E1-c | before_modification | — | 2 | b1314aaf7dd21df979776b80377773b064992061b8e76d7da9fb63054f7ab113 |
| 16 | E1-a | after_observation | — | 3 | 974e18e482da1f33b72c77ef3f3cfb0450f54562a44fb08962f45d8772f82faf |
| 17 | E1-a | before_modification | — | 3 | eaea2ababe9200df6e28d0b58f876262111b9e43a015f3240ecbcf0e0f904be0 |
| 18 | E1-a | after_applied | — | 3 | 69e7e2fe6ab825af9a2c0471fa4c9f7be04e2f8d0058f3f9505aa29c1f3675f1 |
| 19 | E1-b | after_applied | from_scratch | 3 | 703c978fa344d0444ba8531b8977392bc7ce8a83274eea82109bf96581411998 |
| 20 | E1-b | after_applied | full_history | 3 | 17aa74c436bfca5f2f55f353070c5320f78a659a855be8c4f578f4b3e23d7570 |
| 21 | E1-b | after_applied | resume_package | 3 | e25936115ab276824e274ddd762e9d8fdbab9eeedf4fc63b844c039db2af723d |
| 22 | E1-c | before_modification | — | 3 | a30b5a5609f0af960af8a1df554dac2ecda6827644bf51ef29fbcff1d623ba25 |

E1-a: 9 plans; E1-b: 9 plans; E1-c: 3 plans; F12/E5: 1 plan with its existing missing-key control.
All plans share one deployment and identities. Existing runner preconditions, normal close, restoration and independent H00 remain required.
