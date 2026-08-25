# Partial stub for `invoke.tasks`, overriding only this module — every other invoke module keeps its
# inline (`py.typed`) annotations. Exists because invoke declares `task(*args, **kwargs) -> Callable`
# (bare `Callable` = `Callable[..., Unknown]`), so `@task` erases the decorated function's signature
# for every caller: basedpyright reports `reportUntypedFunctionDecorator` at each decorator and
# "partially unknown" wherever a task is referenced (a `pre=[...]` list, a test calling it). The
# `ParamSpec` overloads below make a decorated task keep its own parameters and return type.
# Offered upstream as well; delete this file once a released invoke carries the same signature. See
# plans/2026-08-25-type-check-warning-noise.md.

from collections.abc import Callable, Iterable
from inspect import Signature
from typing import Any, Generic, ParamSpec, TypeVar, overload

from .config import Config
from .context import Context
from .parser import Argument

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T", bound=Callable[..., Any])

class Task(Generic[T]):
    body: T
    aliases: Iterable[str]
    is_default: bool
    positional: list[str]
    optional: tuple[str, ...]
    iterable: Iterable[str]
    incrementable: Iterable[str]
    auto_shortflags: bool
    help: dict[str, Any]
    # Narrower than `__init__`'s parameter on purpose: a task object is what every `pre=[...]` in this
    # family holds, and `Call` answers `.name` too (its `__getattr__` delegates to the task).
    pre: list[Task[Any] | Call]
    post: list[Task[Any] | Call]
    times_called: int
    autoprint: bool
    __name__: str
    __module__: str
    def __init__(
        self,
        body: T,
        name: str | None = None,
        aliases: Iterable[str] = (),
        positional: Iterable[str] | None = None,
        optional: Iterable[str] = (),
        default: bool = False,
        auto_shortflags: bool = True,
        help: dict[str, Any] | None = None,  # noqa: A002 — invoke's own keyword name
        pre: list[Task[Any] | Call | str] | str | None = None,
        post: list[Task[Any] | Call | str] | str | None = None,
        autoprint: bool = False,
        iterable: Iterable[str] | None = None,
        incrementable: Iterable[str] | None = None,
    ) -> None: ...
    @property
    def name(self) -> str: ...
    def __call__(self: Task[Callable[P, R]], *args: P.args, **kwargs: P.kwargs) -> R: ...
    @property
    def called(self) -> bool: ...
    def argspec(self, body: Callable[..., Any]) -> Signature: ...
    def fill_implicit_positionals(self, positional: Iterable[str] | None) -> list[str]: ...
    def arg_options(self, name: str, default: Any, taken_names: set[str]) -> dict[str, Any]: ...
    def get_arguments(self, ignore_unknown_help: bool | None = None) -> list[Argument]: ...

@overload
def task(body: Callable[P, R], /) -> Task[Callable[P, R]]: ...
@overload
def task(
    *pre_tasks: Task[Any] | Call,
    name: str | None = ...,
    aliases: Iterable[str] = ...,
    positional: Iterable[str] | None = ...,
    optional: Iterable[str] = ...,
    default: bool = ...,
    auto_shortflags: bool = ...,
    help: dict[str, Any] | None = ...,
    pre: list[Task[Any] | Call | str] | str | None = ...,
    post: list[Task[Any] | Call | str] | str | None = ...,
    autoprint: bool = ...,
    iterable: Iterable[str] | None = ...,
    incrementable: Iterable[str] | None = ...,
    klass: type[Task[Any]] = ...,
) -> Callable[[Callable[P, R]], Task[Callable[P, R]]]: ...

class Call:
    task: Task[Any]
    called_as: str | None
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    def __init__(
        self,
        task: Task[Any],
        called_as: str | None = None,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> None: ...
    def __getattr__(self, name: str) -> Any: ...
    def __deepcopy__(self, memo: object) -> Call: ...
    def __eq__(self, other: object) -> bool: ...
    def make_context(self, config: Config) -> Context: ...
    def clone_data(self) -> dict[str, Any]: ...
    def clone(self, into: type[Call] | None = None, with_: dict[str, Any] | None = None) -> Call: ...

def call(task: Task[Any], *args: Any, **kwargs: Any) -> Call: ...
