"""quest('<gym>'): the eight Gym beats as runnable quests — travel to the town, into the Gym, then challenge_leader (heal / save_state / the under-levelled warning live there).

quest('brock'|'misty'|'surge'|'erika'|'koga'|'sabrina'|'blaine'|'giovanni') does what the model otherwise strings together by hand: go_to the town, go_to('Gym'), challenge_leader(). A trainer
on the way or the Leader himself ends the call as a battle for the model to play; call quest('<gym>') again to continue (it resumes: inside the Gym it just challenges again). The beat's
`needs` (the chain order) is checked first, so a locked Gym says what comes first instead of walking into a guard."""
from game.state import GameContext
from knowledge.navigation import MAP_NAMES

# key -> (town map, gym map, leader, badge name)
GYMS = {
    "brock": ((3, 2), (6, 2), "Brock", "Boulder"),
    "misty": ((3, 3), (7, 5), "Misty", "Cascade"),
    "surge": ((3, 5), (9, 6), "Lt. Surge", "Thunder"),
    "erika": ((3, 6), (10, 16), "Erika", "Rainbow"),
    "koga": ((3, 7), (11, 3), "Koga", "Soul"),
    "sabrina": ((3, 10), (14, 3), "Sabrina", "Marsh"),
    "blaine": ((3, 8), (12, 0), "Blaine", "Volcano"),
    "giovanni": ((3, 1), (5, 1), "Giovanni", "Earth"),
}


class GymQuestMixin:
    def _get_gym(self, key: str, auto_trainers: bool = False) -> str:
        town, gym, leader, badge = GYMS[key]
        call = f"quest('{key}')"
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        for _ in range(12):
            here = tuple(self.reader.read_current_map())
            if here == gym:
                break
            dest = "Gym" if here == town else MAP_NAMES.get(town)
            out = self._go_to(dest, mode="yield", auto_trainers=auto_trainers, resume_call=call)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if tuple(self.reader.read_current_map()) != gym and any(s in out for s in ("Can't get to", "No route", "Blocked", "gated", "no walking route", "Not travelling yet")):
                return f"Can't get to {leader}'s Gym yet: {out}"
        if tuple(self.reader.read_current_map()) != gym:
            return f"Didn't reach {leader}'s Gym yet — call {call} again to continue (it resumes)."
        out = self._challenge_leader()
        from knowledge.gym_advice import brief
        tip = brief(leader)
        return f"{out} {tip}" if tip and "battle started" in out else out
