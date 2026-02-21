from truthbattle.word_problems import try_solve_incline_friction


def test_incline_friction_accepts_degrees_wording():
    out = try_solve_incline_friction(
        "A body slides down an incline with kinetic friction. "
        "mu = 0.20, angle = 30 degrees, slide is 10 m long, initial velocity is zero."
    )
    assert out is not None
    assert out["name"] == "inclined-plane friction word problem"
    assert "m/s" in out["answer"]
