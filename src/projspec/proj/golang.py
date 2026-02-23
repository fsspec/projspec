from projspec.proj import ProjectSpec


class Golang(ProjectSpec):
    spec_doc = "https://go.dev/doc/modules/gomod-ref"

    def match(self) -> bool:
        return "go.mod" in self.proj.basenames

    def parse(self) -> None:
        # TODO: probably `go run` or `go build` artifacts
        # dependencies via the require keyword
        pass

    @staticmethod
    def _create(path: str) -> None:
        # https://go.dev/doc/tutorial/getting-started
        with open(f"{path}/go.mod", "w") as f:
            f.write("module example.com/hello")
        with open(f"{path}/hello.go", "w") as f:
            f.write(
                """package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}
"""
            )
