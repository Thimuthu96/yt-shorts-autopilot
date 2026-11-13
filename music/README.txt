Music for Gus Explains (royalty-free only).

1. In YouTube Studio open Audio Library and download tracks, preferring "No attribution required".
2. Put each .mp3 in this folder and add an entry for it in tracks.yaml:
     - file: "Track Name.mp3"
       title: "Track Name"
       artist: "Artist"
       attribution: null          # or the exact attribution text the library asks for
       facebook_ok: false         # true only if the licence allows Facebook too
       moods: [curious, tense]    # curious | tense | upbeat | epic
3. Each video picks one track that matches its mood, deterministically from the slug, and mixes it
   quietly under the voice. Facebook Reels only get tracks with facebook_ok: true.
   With no tracks listed, videos are voice and sound effects only.
