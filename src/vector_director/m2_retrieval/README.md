# M2: the gallery and its search

Every prop and backdrop, registered once, for any project. See `library.py` for the format.

```bash
vd library seed --sadhu ../sadhu                                  # Sadhu's assets, objects, AI props and sets
vd library openmoji --heights data/raw/openmoji/heights.json      # the open-licence set, unpacked in data/raw/openmoji
vd library thumbs                                                 # a picture of each item
vd library embed                                                  # CLIP vectors of each picture and its words
vd library eval                                                   # recall@10 and MRR on data/eval/retrieval.jsonl
vd search "stone well"
vd serve                                                          # for Studio's Gallery tab, on port 8772
```

Re-seeding keeps your edits. `library/thumbs` and `library/vectors.npz` are rebuilt, not committed.

M4 plugs fine-tuned weights into `ClipEmbedder`. `CrossEncoderReranker` is still a stub.
