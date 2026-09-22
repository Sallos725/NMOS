# NMOS Phase 0A spike report

Observation files: 66

- environment: `{"cryptoSubtleAvailable": true, "hashMethod": "crypto.subtle", "isSecureContext": true, "spikeVersion": "0.2.0", "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/148.0.0.0 Safari/537.36"}`

## S1

- beforeRequest seq=5 mode=`model` actionCount=1 formatedCount=1 formatedHash=6a1969ad5e msgs=9 ~tok=342 lastRole=user hostTail=user userExact=True dtPrev=5703ms getChat=0.6ms `20260922T062816.095399Z__S1__beforeRequest__fcf0b154.json`
- output idx=7 tail=True chatId=9fc87c88-f1e4-4096-b759-c5c21591f285 generationId=9fc87c88-f1e4-4096-b759-c5c21591f285 swipe=None/0 `20260922T062816.113803Z__S1__output__438e86f7.json`

## S1-after

- snapshot msgs=8 bytes=2531 getChat=0.5ms hash=0.4ms (crypto.subtle) `20260922T062820.226735Z__S1-after__snapshot__2f80e804.json`

## S1-before

- snapshot msgs=6 bytes=1941 getChat=0.5ms hash=0.4ms (crypto.subtle) `20260922T062814.027565Z__S1-before__snapshot__9ad1e4e6.json`

## S10-after

- snapshot msgs=8 bytes=2971 getChat=0.5ms hash=1.2ms (crypto.subtle) `20260922T064327.818700Z__S10-after__snapshot__d92d4e35.json`

## S10-before

- snapshot msgs=8 bytes=2971 getChat=0.6ms hash=0.4ms (crypto.subtle) `20260922T064317.729359Z__S10-before__snapshot__ae5766da.json`
- loaded `20260922T064319.623571Z__S10-before__loaded__1d056c9e.json`

## S10-import-current-index

- snapshot msgs=0 bytes=195 getChat=0.3ms hash=0.1ms (crypto.subtle) `20260922T064417.524673Z__S10-import-current-index__snapshot__52612d7e.json`

## S10-imported

- snapshot msgs=8 bytes=2971 getChat=0.3ms hash=0.4ms (crypto.subtle) `20260922T064433.841996Z__S10-imported__snapshot__63edf8e2.json`

## S11

- beforeRequest seq=1 mode=`submodel` actionCount=1 formatedCount=1 formatedHash=2ae4ace63b msgs=2 ~tok=423 lastRole=user hostTail=char userExact=False dtPrev=Nonems getChat=0.5ms `20260922T064457.941862Z__S11__beforeRequest__66656fcd.json`

## S11-after

- snapshot msgs=8 bytes=2992 getChat=0.5ms hash=0.3ms (crypto.subtle) `20260922T064502.027850Z__S11-after__snapshot__d5fa708d.json`

## S11-before

- snapshot msgs=8 bytes=2971 getChat=0.5ms hash=0.5ms (crypto.subtle) `20260922T064455.830989Z__S11-before__snapshot__0383a498.json`

## S12

- beforeRequest seq=2 mode=`model` actionCount=1 formatedCount=1 formatedHash=94f5d11cf0 msgs=7 ~tok=357 lastRole=user hostTail=user userExact=True dtPrev=25190ms getChat=0.4ms `20260922T064523.131209Z__S12__beforeRequest__24aeb578.json`
- beforeRequest seq=3 mode=`model` actionCount=2 formatedCount=2 formatedHash=94f5d11cf0 msgs=7 ~tok=357 lastRole=user hostTail=user userExact=True dtPrev=8ms getChat=0.3ms `20260922T064523.138781Z__S12__beforeRequest__09a8efe5.json`
- beforeRequest seq=4 mode=`model` actionCount=3 formatedCount=3 formatedHash=94f5d11cf0 msgs=7 ~tok=357 lastRole=user hostTail=user userExact=True dtPrev=7ms getChat=0.5ms `20260922T064523.147685Z__S12__beforeRequest__2ebc2520.json`
- output idx=9 tail=True chatId=dd5bcde7-5811-41e1-a798-617f18525af2 generationId=dd5bcde7-5811-41e1-a798-617f18525af2 swipe=None/0 `20260922T064523.163037Z__S12__output__2df1473b.json`
- beforeRequest seq=5 mode=`submodel` actionCount=1 formatedCount=1 formatedHash=3f79808779 msgs=2 ~tok=458 lastRole=user hostTail=char userExact=False dtPrev=17ms getChat=1ms `20260922T064523.166806Z__S12__beforeRequest__344e70ea.json`

## S12-after

- snapshot msgs=10 bytes=3607 getChat=0.5ms hash=0.5ms (crypto.subtle) `20260922T064532.026773Z__S12-after__snapshot__00fd15a7.json`

## S12-before

- snapshot msgs=8 bytes=2992 getChat=0.5ms hash=0.5ms (crypto.subtle) `20260922T064521.408222Z__S12-before__snapshot__b9ac13e5.json`

## S14-100-hash

- hashBenchmark msgs=100 bytes=40765 subtle=0.8000001907348633ms fallback=4.399999618530273ms agree=True `20260922T064649.779572Z__S14-100-hash__hashBenchmark__d16b83aa.json`

## S14-100-run1

- snapshot msgs=100 bytes=30292 getChat=3.1ms hash=3.1ms (crypto.subtle) `20260922T064640.765424Z__S14-100-run1__snapshot__e6f5c199.json`

## S14-100-run2

- snapshot msgs=100 bytes=30292 getChat=2.5ms hash=2.4ms (crypto.subtle) `20260922T064643.767269Z__S14-100-run2__snapshot__4f77b5a5.json`

## S14-100-run3

- snapshot msgs=100 bytes=30292 getChat=3.1ms hash=2.5ms (crypto.subtle) `20260922T064646.775264Z__S14-100-run3__snapshot__270a001b.json`

## S14-1000-hash

- hashBenchmark msgs=1000 bytes=413048 subtle=6.100000381469727ms fallback=16.899999618530273ms agree=True `20260922T064708.936424Z__S14-1000-hash__hashBenchmark__d2f223a4.json`

## S14-1000-run1

- snapshot msgs=1000 bytes=307176 getChat=13ms hash=19.9ms (crypto.subtle) `20260922T064659.926267Z__S14-1000-run1__snapshot__bc025505.json`

## S14-1000-run2

- snapshot msgs=1000 bytes=307176 getChat=11.9ms hash=19.3ms (crypto.subtle) `20260922T064702.928109Z__S14-1000-run2__snapshot__c804f5f8.json`

## S14-1000-run3

- snapshot msgs=1000 bytes=307176 getChat=15.7ms hash=32.3ms (crypto.subtle) `20260922T064705.964878Z__S14-1000-run3__snapshot__3f3d78f7.json`

## S14-1000-send

- beforeRequest seq=6 mode=`model` actionCount=1 formatedCount=1 formatedHash=f4ced352d3 msgs=81 ~tok=4550 lastRole=user hostTail=user userExact=True dtPrev=121646ms getChat=12.6ms `20260922T064724.829329Z__S14-1000-send__beforeRequest__d4a2832b.json`
- output idx=1001 tail=True chatId=50b2542c-ab65-4a1d-a11a-e5adfa3d44a9 generationId=50b2542c-ab65-4a1d-a11a-e5adfa3d44a9 swipe=None/0 `20260922T064724.921036Z__S14-1000-send__output__5eb2d224.json`
- beforeRequest seq=7 mode=`submodel` actionCount=1 formatedCount=1 formatedHash=173ca43148 msgs=2 ~tok=764 lastRole=user hostTail=char userExact=False dtPrev=77ms getChat=33.7ms `20260922T064724.967458Z__S14-1000-send__beforeRequest__e248391e.json`

## S2

- beforeRequest seq=1 mode=`model` actionCount=1 formatedCount=1 formatedHash=6a1969ad5e msgs=9 ~tok=342 lastRole=user hostTail=user userExact=True dtPrev=Nonems getChat=4.2ms `20260922T063336.334127Z__S2__beforeRequest__233925c8.json`
- output idx=7 tail=True chatId=eb2bc3bc-1be2-4c95-a67e-ca511c8f812c generationId=eb2bc3bc-1be2-4c95-a67e-ca511c8f812c swipe=None/0 `20260922T063336.355574Z__S2__output__1979b538.json`

## S2-after

- snapshot msgs=8 bytes=2752 getChat=0.4ms hash=0.4ms (crypto.subtle) `20260922T063340.162324Z__S2-after__snapshot__288b0013.json`

## S2-before

- snapshot msgs=8 bytes=2551 getChat=0.6ms hash=1.7ms (crypto.subtle) `20260922T063232.850537Z__S2-before__snapshot__0e3b9de9.json`

## S3-after

- snapshot msgs=8 bytes=2752 getChat=0.5ms hash=0.3ms (crypto.subtle) `20260922T063344.903119Z__S3-after__snapshot__8864c911.json`

## S3-before

- snapshot msgs=8 bytes=2752 getChat=0.4ms hash=0.2ms (crypto.subtle) `20260922T063341.669304Z__S3-before__snapshot__7d594fb1.json`

## S4

- beforeRequest seq=2 mode=`model` actionCount=1 formatedCount=1 formatedHash=057d902c0e msgs=12 ~tok=374 lastRole=system hostTail=user userExact=True dtPrev=29297ms getChat=0.5ms `20260922T063405.625235Z__S4__beforeRequest__caabffb2.json`
- output idx=8 tail=True chatId=bd4063ab-6a7a-4690-9c31-76a14ef8ae2f generationId=f5a7efbe-57b4-40b9-81a7-8d8984fed045 swipe=None/0 `20260922T063405.650334Z__S4__output__b392b0e4.json`

## S4-after

- snapshot msgs=9 bytes=3224 getChat=0.5ms hash=0.5ms (crypto.subtle) `20260922T063409.137891Z__S4-after__snapshot__e440a92f.json`

## S4-before

- snapshot msgs=8 bytes=2752 getChat=0.5ms hash=0.4ms (crypto.subtle) `20260922T063403.501103Z__S4-before__snapshot__abc5171c.json`

## S4b

- beforeRequest seq=3 mode=`model` actionCount=1 formatedCount=1 formatedHash=a6cdc3c7b1 msgs=12 ~tok=394 lastRole=system hostTail=char userExact=True dtPrev=176291ms getChat=0.3ms `20260922T063701.914161Z__S4b__beforeRequest__4f40935b.json`
- output idx=8 tail=True chatId=bd4063ab-6a7a-4690-9c31-76a14ef8ae2f generationId=3fcd6377-138d-459a-a60d-4c715e49a890 swipe=None/0 `20260922T063701.931967Z__S4b__output__8cc935bd.json`

## S4b-after

- snapshot msgs=9 bytes=3312 getChat=0.4ms hash=0.3ms (crypto.subtle) `20260922T063705.418632Z__S4b-after__snapshot__0967f280.json`
- loaded `20260922T064040.045419Z__S4b-after__loaded__7cc2ab5e.json`

## S4b-before

- snapshot msgs=9 bytes=3224 getChat=0.5ms hash=1ms (crypto.subtle) `20260922T063659.828834Z__S4b-before__snapshot__91582268.json`

## S5-after

- snapshot msgs=9 bytes=3327 getChat=0.5ms hash=0.8ms (crypto.subtle) `20260922T064109.568108Z__S5-after__snapshot__7df4c0de.json`

## S5-before

- snapshot msgs=9 bytes=3312 getChat=0.5ms hash=1.7ms (crypto.subtle) `20260922T064105.799058Z__S5-before__snapshot__43b040ac.json`

## S6-after

- snapshot msgs=9 bytes=3342 getChat=0.4ms hash=0.5ms (crypto.subtle) `20260922T064114.782819Z__S6-after__snapshot__71602657.json`
- loaded `20260922T064135.839089Z__S6-after__loaded__d965d326.json`

## S6-before

- snapshot msgs=9 bytes=3327 getChat=0.4ms hash=0.4ms (crypto.subtle) `20260922T064111.072339Z__S6-before__snapshot__b44f9f18.json`

## S7-after

- snapshot msgs=8 bytes=2921 getChat=0.6ms hash=0.3ms (crypto.subtle) `20260922T064243.423614Z__S7-after__snapshot__15dc2df6.json`

## S7-before

- snapshot msgs=9 bytes=3381 getChat=0.6ms hash=1.4ms (crypto.subtle) `20260922T064239.821794Z__S7-before__snapshot__d40f3bbb.json`

## S8-after

- snapshot msgs=9 bytes=3358 getChat=0.5ms hash=0.3ms (crypto.subtle) `20260922T064158.001072Z__S8-after__snapshot__371986e1.json`
- loaded `20260922T064159.681715Z__S8-after__loaded__5d79ccc7.json`

## S8-before

- snapshot msgs=9 bytes=3342 getChat=0.5ms hash=1.5ms (crypto.subtle) `20260922T064154.894167Z__S8-before__snapshot__9d600d16.json`

## S8b-after

- snapshot msgs=9 bytes=3381 getChat=0.5ms hash=0.5ms (crypto.subtle) `20260922T064210.351271Z__S8b-after__snapshot__a676edb0.json`
- loaded `20260922T064221.257984Z__S8b-after__loaded__254c0f00.json`

## S8b-before

- snapshot msgs=9 bytes=3358 getChat=0.9ms hash=1.8ms (crypto.subtle) `20260922T064207.246098Z__S8b-before__snapshot__e13d93b0.json`

## S9-after

- snapshot msgs=5 bytes=1699 getChat=0.5ms hash=0.3ms (crypto.subtle) `20260922T064257.816592Z__S9-after__snapshot__4648e1cd.json`
  - marker at position 4: `{{specialcomment::branchedfrom::26b153b7-fc92-44da-872e-72499dee0b08::New Chat 2::a3f81796-18cc-42fd-9306-78371f3e68a1::}}`

## S9-before

- snapshot msgs=8 bytes=2921 getChat=0.4ms hash=0.5ms (crypto.subtle) `20260922T064254.333907Z__S9-before__snapshot__1f58059b.json`

## warmup

- beforeRequest seq=2 mode=`model` actionCount=1 formatedCount=1 formatedHash=26f1967ea2 msgs=3 ~tok=259 lastRole=user hostTail=user userExact=True dtPrev=22172ms getChat=0.2ms `20260922T062805.356136Z__warmup__beforeRequest__82612512.json`
- output idx=1 tail=True chatId=41b095dc-1b29-4899-b83c-ef8a2d0996d6 generationId=41b095dc-1b29-4899-b83c-ef8a2d0996d6 swipe=None/0 `20260922T062805.370381Z__warmup__output__691c4846.json`
- beforeRequest seq=3 mode=`model` actionCount=1 formatedCount=1 formatedHash=8db9997325 msgs=5 ~tok=285 lastRole=user hostTail=user userExact=True dtPrev=2516ms getChat=0.3ms `20260922T062807.869144Z__warmup__beforeRequest__a3e04a86.json`
- output idx=3 tail=True chatId=a3f81796-18cc-42fd-9306-78371f3e68a1 generationId=a3f81796-18cc-42fd-9306-78371f3e68a1 swipe=None/0 `20260922T062807.883112Z__warmup__output__ef8bdaca.json`
- beforeRequest seq=4 mode=`model` actionCount=1 formatedCount=1 formatedHash=576eee382c msgs=7 ~tok=315 lastRole=user hostTail=user userExact=True dtPrev=2517ms getChat=0.4ms `20260922T062810.388620Z__warmup__beforeRequest__b828a53f.json`
- output idx=5 tail=True chatId=5e2370a0-2971-488c-a35b-fc9cc5b2b679 generationId=5e2370a0-2971-488c-a35b-fc9cc5b2b679 swipe=None/0 `20260922T062810.402269Z__warmup__output__dd67afca.json`

# Before/after manifest diffs

## S1

- files: `20260922T062814.027565Z__S1-before__snapshot__9ad1e4e6.json` → `20260922T062820.226735Z__S1-after__snapshot__2f80e804.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 6 → 8 (kept ids 6)
- removed ids: none
- added ids: [(6, 'fda7d327-b187-48b4-af8f-2a560be822ef', 'user'), (7, '9fc87c88-f1e4-4096-b759-c5c21591f285', 'char')]
- changed on kept ids: none

## S10

- files: `20260922T064317.729359Z__S10-before__snapshot__ae5766da.json` → `20260922T064327.818700Z__S10-after__snapshot__d92d4e35.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 8 → 8 (kept ids 8)
- removed ids: none
- added ids: none
- changed on kept ids: none

## S11

- files: `20260922T064455.830989Z__S11-before__snapshot__0383a498.json` → `20260922T064502.027850Z__S11-after__snapshot__d5fa708d.json`
- host chat id: 04fcdbc9-5c3c-4502-8039-c8df6f98bcb7 → 04fcdbc9-5c3c-4502-8039-c8df6f98bcb7
- messages: 8 → 8 (kept ids 8)
- removed ids: none
- added ids: none
- changed on kept ids: none

## S12

- files: `20260922T064521.408222Z__S12-before__snapshot__b9ac13e5.json` → `20260922T064532.026773Z__S12-after__snapshot__00fd15a7.json`
- host chat id: 04fcdbc9-5c3c-4502-8039-c8df6f98bcb7 → 04fcdbc9-5c3c-4502-8039-c8df6f98bcb7
- messages: 8 → 10 (kept ids 8)
- removed ids: none
- added ids: [(8, '603d5563-1310-42a3-a44d-1911e711a998', 'user'), (9, 'dd5bcde7-5811-41e1-a798-617f18525af2', 'char')]
- changed on kept ids: none

## S2

- files: `20260922T063232.850537Z__S2-before__snapshot__0e3b9de9.json` → `20260922T063340.162324Z__S2-after__snapshot__288b0013.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 8 → 8 (kept ids 7)
- removed ids: [(7, '9fc87c88-f1e4-4096-b759-c5c21591f285', 'char')]
- added ids: [(7, 'eb2bc3bc-1be2-4c95-a67e-ca511c8f812c', 'char')]
- changed on kept ids: none

## S3

- files: `20260922T063341.669304Z__S3-before__snapshot__7d594fb1.json` → `20260922T063344.903119Z__S3-after__snapshot__8864c911.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 8 → 8 (kept ids 8)
- removed ids: none
- added ids: none
- changed on kept ids:
  - `eb2bc3bc-1be2-4c95-a67e-ca511c8f812c`: swipeId: 1→0, contentHash: 4f05b2991c86→963ebac157a0, dataHash: 44f405b063f3→e0713ad452cf

## S4

- files: `20260922T063403.501103Z__S4-before__snapshot__abc5171c.json` → `20260922T063409.137891Z__S4-after__snapshot__e440a92f.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 8 → 9 (kept ids 8)
- removed ids: none
- added ids: [(8, 'bd4063ab-6a7a-4690-9c31-76a14ef8ae2f', 'char')]
- changed on kept ids: none

## S4b

- files: `20260922T063659.828834Z__S4b-before__snapshot__91582268.json` → `20260922T063705.418632Z__S4b-after__snapshot__0967f280.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 9 → 9 (kept ids 9)
- removed ids: none
- added ids: none
- changed on kept ids:
  - `bd4063ab-6a7a-4690-9c31-76a14ef8ae2f`: generationId: f5a7efbe-57b→3fcd6377-138, contentHash: 5766fc9e1614→02527ccbbcf8, dataHash: 2d70a0521e4a→29539961bb77

## S5

- files: `20260922T064105.799058Z__S5-before__snapshot__43b040ac.json` → `20260922T064109.568108Z__S5-after__snapshot__7df4c0de.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 9 → 9 (kept ids 9)
- removed ids: none
- added ids: none
- changed on kept ids:
  - `f3c47d86-a49d-4dca-bec8-e576f55fe576`: contentHash: 4a8980be0262→e50b41e55e6d, dataHash: 997edfc6d9bc→47b9911666a7

## S6

- files: `20260922T064111.072339Z__S6-before__snapshot__b44f9f18.json` → `20260922T064114.782819Z__S6-after__snapshot__71602657.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 9 → 9 (kept ids 9)
- removed ids: none
- added ids: none
- changed on kept ids:
  - `a3f81796-18cc-42fd-9306-78371f3e68a1`: contentHash: e0a43b5d51dc→bc9486dd849a, dataHash: 85f5cda7e471→f5e12577c908

## S7

- files: `20260922T064239.821794Z__S7-before__snapshot__d40f3bbb.json` → `20260922T064243.423614Z__S7-after__snapshot__15dc2df6.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 9 → 8 (kept ids 8)
- removed ids: [(5, '5e2370a0-2971-488c-a35b-fc9cc5b2b679', 'char')]
- added ids: none
- changed on kept ids:
  - `fda7d327-b187-48b4-af8f-2a560be822ef`: position: 6→5
  - `eb2bc3bc-1be2-4c95-a67e-ca511c8f812c`: position: 7→6
  - `bd4063ab-6a7a-4690-9c31-76a14ef8ae2f`: position: 8→7

## S8

- files: `20260922T064154.894167Z__S8-before__snapshot__9d600d16.json` → `20260922T064158.001072Z__S8-after__snapshot__371986e1.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 9 → 9 (kept ids 9)
- removed ids: none
- added ids: none
- changed on kept ids:
  - `6fcccbc7-4983-4e8d-82dc-865f7eb5f53c`: disabled: ∅→True, contentHash: e067f1f0512f→ef7218bf8fe1

## S8b

- files: `20260922T064207.246098Z__S8b-before__snapshot__e13d93b0.json` → `20260922T064210.351271Z__S8b-after__snapshot__a676edb0.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 26b153b7-fc92-44da-872e-72499dee0b08
- messages: 9 → 9 (kept ids 9)
- removed ids: none
- added ids: none
- changed on kept ids:
  - `f3c47d86-a49d-4dca-bec8-e576f55fe576`: disabled: ∅→allBefore, contentHash: e50b41e55e6d→985088da5c65

## S9

- files: `20260922T064254.333907Z__S9-before__snapshot__1f58059b.json` → `20260922T064257.816592Z__S9-after__snapshot__4648e1cd.json`
- host chat id: 26b153b7-fc92-44da-872e-72499dee0b08 → 0455fcdf-edf6-4bc3-9ac1-121e96ff9ee1
- messages: 8 → 5 (kept ids 0)
- removed ids: [(0, '1a966c29-dabb-4ba0-ac07-93805d3a6a1a', 'user'), (1, '41b095dc-1b29-4899-b83c-ef8a2d0996d6', 'char'), (2, 'f3c47d86-a49d-4dca-bec8-e576f55fe576', 'user'), (3, 'a3f81796-18cc-42fd-9306-78371f3e68a1', 'char'), (4, '6fcccbc7-4983-4e8d-82dc-865f7eb5f53c', 'user'), (5, 'fda7d327-b187-48b4-af8f-2a560be822ef', 'user'), (6, 'eb2bc3bc-1be2-4c95-a67e-ca511c8f812c', 'char'), (7, 'bd4063ab-6a7a-4690-9c31-76a14ef8ae2f', 'char')]
- added ids: [(0, 'e643c4bb-05de-44dc-bbf6-f0e6bf80799d', 'user'), (1, '1bacdd42-fd98-44b7-a3b9-a11ff29899e1', 'char'), (2, 'd383ead0-031b-4b07-bcec-d0432cd5b2f1', 'user'), (3, 'a90c4942-955a-4cd5-af06-cab6646059f9', 'char'), (4, 'cdf45692-5cfd-4b50-9994-c5048df29b84', 'char')]
- changed on kept ids: none

