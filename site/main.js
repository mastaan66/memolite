// typing terminal + copy buttons. No deps.
(function () {
  var lines = [
    { t: "$ pip install memolite", c: "p" },
    { t: "$ memolite autoinstall --db agent.db", c: "p" },
    { t: "installed agent.db - every Python here now remembers.", c: "c" },
    { t: "$ python -c \"from memolite import MemoryStore; s=MemoryStore('agent.db'); print(s.recall('deploy').prompt)\"", c: "p" },
    { t: "# Long-term memories\n- [semantic] Deploy key rotates every Friday", c: "c" }
  ];
  var el = document.getElementById("term");
  if (!el) return;
  var li = 0, ci = 0, cur = null;
  function tick() {
    if (li >= lines.length) return;
    var line = lines[li];
    if (!cur) { cur = document.createElement("div"); cur.className = line.c; el.appendChild(cur); ci = 0; }
    cur.textContent = line.t.slice(0, ++ci);
    if (ci >= line.t.length) { li++; cur = null; setTimeout(tick, 450); }
    else setTimeout(tick, 18);
  }
  var seen = false;
  function start() {
    if (seen) return; seen = true; tick();
  }
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (e) { if (e[0].isIntersecting) start(); }).observe(el);
  } else { start(); }

  var snippets = {
    patch: 'from memolite import MemoryStore, patch_openai\n\nstore = MemoryStore("agent.db")\npatch_openai(client, store, session="s1")',
    auto: 'memolite autoinstall --db agent.db\nMEMOLITE_OFF=1 python app.py  # kill-switch',
    emb: 'Config(embedder=openai_embedder(client))\n# or local_embedder() / ollama_embedder()',
    install: 'pip install memolite\nmemolite autoinstall --db agent.db'
  };
  document.querySelectorAll(".copy").forEach(function (b) {
    b.addEventListener("click", function () {
      var txt = snippets[b.dataset.copy] || "";
      if (navigator.clipboard) navigator.clipboard.writeText(txt);
      b.textContent = "copied";
      setTimeout(function () { b.textContent = "copy"; }, 1200);
    });
  });
})();
