"""Word of mouth, no LLM: what ring n heard this tick reaches ring n+1 next tick."""


def update(memo, ring_heard):
    """ring_heard: {ring: parsed ear answers}. Stores each ring's message for the next tick."""
    word = {}
    for ring, heard in ring_heard.items():
        if not heard or not heard.get("drop_eta"):
            continue
        eta = heard["drop_eta"]
        word[ring] = {"drop_eta": eta, "p": heard["drop_eta_probs"].get(eta, 0.0), "rising": heard["rising"]}
    memo["word"] = word


def line_for(memo, ring):
    """The line an agent in `ring` hears from the ring in front of it, or ''."""
    msg = memo.get("word", {}).get(ring - 1)
    if not msg:
        return "", {}
    text = f"Word from ring {ring - 1}: drop {msg['drop_eta']} ({msg['p']:.2f}), energy rising {msg['rising']:.2f}."
    return text, {"from_ring": ring - 1, **msg}
