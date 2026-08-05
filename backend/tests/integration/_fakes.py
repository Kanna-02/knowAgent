from __future__ import annotations

from typing import Self


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.commands: list[tuple[str, tuple[object, ...]]] = []

    def setex(self, *args: object) -> Self:
        self.commands.append(("setex", args))
        return self

    def sadd(self, *args: object) -> Self:
        self.commands.append(("sadd", args))
        return self

    def expire(self, *args: object) -> Self:
        self.commands.append(("expire", args))
        return self

    def incr(self, *args: object) -> Self:
        self.commands.append(("incr", args))
        return self

    def delete(self, *args: object) -> Self:
        self.commands.append(("delete", args))
        return self

    def srem(self, *args: object) -> Self:
        self.commands.append(("srem", args))
        return self

    def execute(self) -> list[object]:
        results = [getattr(self.redis, name)(*args) for name, args in self.commands]
        self.commands.clear()
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str | int] = {}
        self.sets: dict[str, set[str]] = {}

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        del transaction
        return FakePipeline(self)

    def setex(self, key: object, ttl: object, value: object) -> bool:
        del ttl
        self.values[str(key)] = str(value)
        return True

    def get(self, key: object) -> str | int | None:
        return self.values.get(str(key))

    def set(self, key: object, value: object, *, ex: int) -> bool:
        assert ex > 0
        self.values[str(key)] = str(value)
        return True

    def getdel(self, key: object) -> str | int | None:
        return self.values.pop(str(key), None)

    def delete(self, *keys: object) -> int:
        deleted = 0
        for key in keys:
            text = str(key)
            deleted += int(text in self.values or text in self.sets)
            self.values.pop(text, None)
            self.sets.pop(text, None)
        return deleted

    def sadd(self, key: object, *members: object) -> int:
        target = self.sets.setdefault(str(key), set())
        before = len(target)
        target.update(str(member) for member in members)
        return len(target) - before

    def srem(self, key: object, *members: object) -> int:
        target = self.sets.setdefault(str(key), set())
        before = len(target)
        target.difference_update(str(member) for member in members)
        return before - len(target)

    def smembers(self, key: object) -> set[str]:
        return set(self.sets.get(str(key), set()))

    def expire(self, key: object, ttl: object) -> bool:
        del ttl
        return str(key) in self.values or str(key) in self.sets

    def incr(self, key: object) -> int:
        text = str(key)
        value = int(self.values.get(text, 0)) + 1
        self.values[text] = value
        return value


__all__ = ["FakePipeline", "FakeRedis"]
