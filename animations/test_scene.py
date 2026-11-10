from manim import *


class HelloManim(Scene):
    def construct(self):
        title = Text("Hello, Raahat!", color=BLUE)
        circle = Circle(color=RED)
        self.play(Write(title))
        self.play(title.animate.shift(UP))
        self.play(Create(circle))
        self.play(circle.animate.scale(1.5))
        self.wait(1)

