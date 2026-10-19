# Repair revalidation plan review scope

Prepared and validated only. No execution authorization was generated.

Run order 1–4 covers four distinct conditions; review actual results before repeats. Run serially.

| Order | Case | Point | Method | Repeat | Plan SHA256 |
|---:|---|---|---|---:|---|
| 1 | E1-a | after_observation | — | 1 | b8f9469abcd65dc66005b3005c46194c0819ab86bbc714d26ccaf5dd3022f65b |
| 2 | E1-b | after_applied | from_scratch | 1 | 10e651a92d0f2469adb0971653394664b1dc386f209eab6f3b144b36a3f38048 |
| 3 | E1-b | after_applied | full_history | 1 | 675f1266afe21bca44029ad42ebf95eb15d7573cf043c8b02b161f23e4eb7db1 |
| 4 | E1-b | after_applied | resume_package | 1 | 67fafc5b3efd0627e0bf758da9498433a44517f1ce8114cdc937ec398344016a |
| 5 | E1-a | after_observation | — | 2 | af79bdc6773b9cc418b20c624a2ffa7f1d7a2d3f818870ffe8db2532e2b09023 |
| 6 | E1-b | after_applied | from_scratch | 2 | a95aa9e1545a2d29ba09a9bea7ed927564409f32b7eedc7490312cc61836823c |
| 7 | E1-b | after_applied | full_history | 2 | 13032005484a64cbbe5922680e94d9300e28c183448fa56a304ca888e8bf0e7a |
| 8 | E1-b | after_applied | resume_package | 2 | b7bede5ee4fe0825a3cfc71d724a990356223a8778119a5c9731c728a1533636 |
| 9 | E1-a | after_observation | — | 3 | 0d1a0c8fd4c6fe0bd59493d4be6e3282d15d862b9dbfee748175377b9639818a |
| 10 | E1-b | after_applied | from_scratch | 3 | d0291b8daf0c106765689cf8e15ed1c5d9b4788801ce1431d0ae730c617d6f95 |
| 11 | E1-b | after_applied | full_history | 3 | 78d6aeb0131c0273aab42ac660fd3bf010a3a7c3ecba2dd632433190233a9997 |
| 12 | E1-b | after_applied | resume_package | 3 | 329f193a374a19f4007b99d568d189f317a02029a3af1201af8bd7ddeda83f44 |

E1-a after_observation: 3 plans; E1-b after_applied: three methods × 3, nine plans.
This batch has no E1-c, F12/E5 or other E1-a points. Old results retain their original frozen source and verdicts.
All plans share one deployment and seven identities. Existing runner preconditions, normal SDK close (including failure cleanup), restoration and independent H00 remain required.
The source/image/configuration binding does not itself prove runtime acceptance or provide authorization.
