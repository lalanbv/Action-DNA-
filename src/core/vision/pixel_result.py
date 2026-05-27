"""像素搜索结果数据结构"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PixelSearchResult:
    """像素搜索结果（不可变）"""

    found: bool
    positions: tuple[tuple[int, int], ...] = ()
    count: int = 0
    search_region: tuple[int, int, int, int] | None = None

    @classmethod
    def not_found(cls) -> "PixelSearchResult":
        return cls(found=False)

    @classmethod
    def found_pixels(
        cls,
        positions: list[tuple[int, int]],
        region: tuple[int, int, int, int] | None = None,
    ) -> "PixelSearchResult":
        return cls(
            found=True,
            positions=tuple(positions),
            count=len(positions),
            search_region=region,
        )

    @property
    def first(self) -> tuple[int, int] | None:
        """第一个匹配位置"""
        return self.positions[0] if self.positions else None

    @property
    def center_of_mass(self) -> tuple[int, int] | None:
        """匹配像素的质心坐标"""
        if not self.positions:
            return None
        n = len(self.positions)
        avg_x = sum(p[0] for p in self.positions) // n
        avg_y = sum(p[1] for p in self.positions) // n
        return (avg_x, avg_y)
