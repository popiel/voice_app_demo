## Voice processing application demo

## Problem statement

As a person with certain types of hearing loss, I want an application that processes audio streams (particularly podcasts) to rebalance and pitch-shift voice vs. background sound (noise and/or music) so that I can better understand the voices.

Processing should be triggered by the submission of an audio stream (or discovery of a newly posted audio stream from one of my favorite podcast sources).
The result should be a remixed audio stream where the voices are always at least 2 decibels higher than any other audio mixed into the stream in their respective highest-energy frequencies, achieved by attenuating the non-voice sound, with a 3-second smooth step applied to the attentuation both before and after the attenuation so that it's not a jarring volume shift.
Furthermore, voices that are dominantly in the 220Hz to 440Hz frequency band should have an extra harmonic added one octave lower, with a harmonic energy half that of the primary voice pitch, and the entire voice energy adjusted so the new remixed voice has the same total energy that the original voice had.
This new audio should be made available on a private website along with links to the original audio and a summary of the contents of the entire audio stream, plus a list of all modifications made to the stream and the time marks where those modifications began and ended.


## Major decisions

1. Submission queue and async processing.  Trying to do this in true real time is a harder problem than I wanted to deal with for a simple demo.
2. Let the agent do _all_ the coding.  Normally I would actively review the code itself, but the judgement criteria explicitly _excluded_ code polish, test coverage, and production readiness.
3. Tech stack: fully free options only, even excluding free evaluation periods for commercial products.  This _lowered_ the quality target, but I couldn't be sure that my evaluation period wouldn't expire before the on-site interview.
4. Website scraping to find podcast downloads was excluded.  I wasn't initially sure of RSS feed availability for my chosen sources, but once those were confirmed, website scraping was explicitly de-scoped.
5. Switch from NPR podcasts to LibriVox with orchestral overlays.  I was expecting an ADA carve-out in the NPR licensing, but after not finding such, going with strictly public domain sources was necessary, given that the on-site interview is a public performance.

## Functionality proof

The deliverable explicitly includes timestamped notations of audio modifications, presented on the website.  These were spot-checked by manually comparing the original audio stream vs. the modified one, testing to see if I could both clearly hear and understand the voice and also hear the music at diminished volume.

## Unexpected failures

My description of pitch shifting failed in multiple ways.
1. My estimate of the frequency band needed to trigger a pitch shift was off by an octave.  I forgot to consider the difference between singing and spoken text.  I lowered the frequency band by an octave to compensate.
2. The overall trigger gate and pitch adjustment scope was poorly phrased.  The AI was being overly local in both trigger criteria and adjustment location, and I had to rephrase prompts to fix it.
3. The actual pitch shift implementation creates annoying buzzing instead of actually pitch-shifting the vocals.  This is again a prompt fault; I specified it as adding a harmonic instead of as pitch-shifting the original to a harmonic target and mixing that in.  A prompt rephrasing will likely fix it, but I ran out of time to implement and verify.

## Time spent

Approximately 5 hours of working with the AI for coding and debugging.  Approximately 1 hour of documentation.

## Agent logs

Agent logs are recorded in the `sessions/` subdirectory.
