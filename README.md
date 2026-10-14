## Voice processing application demo

As a person with certain types of hearing loss, I want an application that processes audio streams (particularly podcasts) to rebalance and pitch-shift voice vs. background sound (noise and/or music) so that I can better understand the voices.

Processing should be triggered by the submission of an audio stream (or discovery of a newly posted audio stream from one of my favorite podcast sources).
The result should be a remixed audio stream where the voices are always at least 2 decibels higher than any other audio mixed into the stream in their respective highest-energy frequencies, achieved by attenuating the non-voice sound, with a 3-second smooth step applied to the attentuation both before and after the attenuation so that it's not a jarring volume shift.
Furthermore, voices that are dominantly in the 220Hz to 440Hz frequency band should have an extra harmonic added one octave lower, with a harmonic energy half that of the primary voice pitch, and the entire voice energy adjusted so the new remixed voice has the same total energy that the original voice had.
This new audio should be made available on a private website along with links to the original audio and a summary of the contents of the entire audio stream, plus a list of all modifications made to the stream and the time marks where those modifications began and ended.

