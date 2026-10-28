/* The Lockman theme: an original dark-hero cue, synthesized live with the Web Audio API.
   D minor, 84 BPM. Low string ostinato, sub drone, taiko hits, a ticking clock,
   and a horn line every other phrase. Nothing plays until the visitor presses the button. */
(function () {
  "use strict";

  var BPM = 84, STEP = 60 / BPM / 4;            // one 16th note
  var CHORDS = [                                 // root (Hz), third offset in semitones
    { root: 73.42, third: 3 },                   // D minor
    { root: 58.27, third: 4 },                   // Bb major
    { root: 49.00, third: 3 },                   // G minor
    { root: 55.00, third: 4 }                    // A major
  ];
  var OSTINATO = [0, 0, 12, 0, 7, 0, 12, 7, 0, 0, 12, 0, 7, 12, 7, 0];
  // horn line for bars 5-8 of each 8-bar phrase: [semitones above D4, length in 16ths]
  var HORN = [[[7, 16]], [[3, 8], [5, 8]], [[12, 8], [8, 8]], [[11, 16]]];
  var D4 = 293.66;

  var ctx, master, verb, timer, step = 0, nextTime = 0, drone, droneGain;

  function semi(f, n) { return f * Math.pow(2, n / 12); }

  function impulse(seconds) {
    var len = ctx.sampleRate * seconds, buf = ctx.createBuffer(2, len, ctx.sampleRate);
    for (var c = 0; c < 2; c++) {
      var d = buf.getChannelData(c);
      for (var i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6);
    }
    return buf;
  }

  function voice(type, freq, t, dur, gain, cutoff, attack, wet) {
    var o = ctx.createOscillator(), o2 = ctx.createOscillator(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    o.type = o2.type = type;
    o.frequency.value = freq; o2.frequency.value = freq; o2.detune.value = 9;
    f.type = "lowpass"; f.frequency.value = cutoff; f.Q.value = 0.7;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(gain, t + attack);
    g.gain.setTargetAtTime(0, t + dur, Math.max(0.05, dur * 0.25));
    o.connect(f); o2.connect(f); f.connect(g); g.connect(master);
    if (wet) { var s = ctx.createGain(); s.gain.value = wet; g.connect(s); s.connect(verb); }
    o.start(t); o2.start(t); o.stop(t + dur * 2 + 1); o2.stop(t + dur * 2 + 1);
  }

  function taiko(t, gain) {
    var o = ctx.createOscillator(), g = ctx.createGain();
    o.type = "sine";
    o.frequency.setValueAtTime(95, t); o.frequency.exponentialRampToValueAtTime(38, t + 0.45);
    g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.9);
    o.connect(g); g.connect(master);
    var s = ctx.createGain(); s.gain.value = 0.35; g.connect(s); s.connect(verb);
    o.start(t); o.stop(t + 1);
  }

  function tick(t) {
    var len = Math.floor(ctx.sampleRate * 0.03), buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
    for (var i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
    var src = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    src.buffer = buf; f.type = "highpass"; f.frequency.value = 3500; g.gain.value = 0.05;
    src.connect(f); f.connect(g); g.connect(master); src.start(t);
  }

  function schedule(t) {
    var bar = Math.floor(step / 16), beat16 = step % 16, chord = CHORDS[bar % 4], phrase = bar % 8;

    // low string ostinato
    voice("sawtooth", semi(chord.root, OSTINATO[beat16]), t, STEP * 0.9, 0.07, 700 + 500 * (phrase / 7), 0.01, 0.15);

    if (beat16 === 0) {
      // sustained brass-like chord and the drone follows the harmony
      [12, 12 + chord.third, 19].forEach(function (n) {
        voice("sawtooth", semi(chord.root, n), t, STEP * 15, 0.028, 520, 1.2, 0.5);
      });
      droneGain.gain.setTargetAtTime(0.16, t, 0.5);
      drone.frequency.setTargetAtTime(chord.root / 2, t, 0.3);
    }
    if (beat16 === 0 || beat16 === 10) taiko(t, beat16 === 0 ? 0.55 : 0.35);
    if (phrase === 7 && beat16 >= 12) taiko(t, 0.25);          // build into the next phrase
    if (beat16 % 4 === 0) tick(t);

    if (phrase >= 4) {
      var pos = 0;
      HORN[phrase - 4].forEach(function (note) {
        if (pos === beat16) voice("square", semi(D4, note[0]), t, STEP * note[1] * 0.95, 0.03, 1400, 0.25, 0.6);
        pos += note[1];
      });
    }
  }

  function loop() {
    while (nextTime < ctx.currentTime + 0.15) {
      schedule(nextTime);
      nextTime += STEP;
      step = (step + 1) % (16 * 8);
    }
  }

  function start() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      var comp = ctx.createDynamicsCompressor();
      master = ctx.createGain(); master.gain.value = 0;
      verb = ctx.createConvolver(); verb.buffer = impulse(3.2);
      verb.connect(master); master.connect(comp); comp.connect(ctx.destination);
      drone = ctx.createOscillator(); drone.type = "sine"; drone.frequency.value = CHORDS[0].root / 2;
      droneGain = ctx.createGain(); droneGain.gain.value = 0;
      drone.connect(droneGain); droneGain.connect(master); drone.start();
    }
    ctx.resume();
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.setTargetAtTime(0.55, ctx.currentTime, 1.2);   // fade in
    step = 0; nextTime = ctx.currentTime + 0.05;
    timer = setInterval(loop, 25);
  }

  function stop() {
    clearInterval(timer);
    if (!ctx) return;
    master.gain.setTargetAtTime(0, ctx.currentTime, 0.35);      // fade out
    setTimeout(function () { if (ctx) ctx.suspend(); }, 1500);
  }

  var btn = document.querySelector(".music-btn");
  if (!btn || !(window.AudioContext || window.webkitAudioContext)) { if (btn) btn.hidden = true; return; }
  btn.addEventListener("click", function () {
    var on = btn.getAttribute("aria-pressed") !== "true";
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.setAttribute("aria-label", on ? "Stop the Lockman theme music" : "Play the Lockman theme music");
    if (on) start(); else stop();
  });
})();
