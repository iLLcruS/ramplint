"""RL107 image-redundant-alt, RL508 label-in-name, RL706 aria-prohibited-attr."""

from __future__ import annotations

import pytest

from ramplint import lint_source


def codes(source: str, code: str) -> list[int]:
    return [v.line for v in lint_source(source) if v.code == code]


# -- RL107 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "alt",
    ["IMG_2031.jpg", "hero banner.PNG", "logo.svg", "image", "Photo", " icon ", "spacer",
     "Picture of a cat", "an image of the team", "Photo showing our office"],
)  # fmt: skip
def test_redundant_alt(alt):
    assert codes(f'<img src="x" alt="{alt}">', "RL107") == [1]


@pytest.mark.parametrize(
    "source",
    [
        '<img src="x" alt="">',
        '<img src="x" alt="Logo">',
        '<img src="x" alt="Photography studio at night">',
        '<img src="x" alt="{{ product.name }}.jpg">',
        '<img src="x">',
        '<img {{ attrs }} alt="photo.jpg">',
        '<a href="/"><img src="c.svg" alt="Cart"> Your cart</a>',
        '<a href="/"><img src="c.svg" alt="Cart"> {{ label }}</a>',
        '<a href="/"><img src="c.svg" alt="Cart"> <span {{ attrs }}>Cart</span></a>',
        '<p><img src="c.svg" alt="Cart"> Cart</p>',
    ],
)
def test_not_redundant(source):
    assert codes(source, "RL107") == []


def test_alt_repeating_button_text():
    source = '<button>\n  <img src="t.svg" alt="Delete">\n  delete\n</button>'
    assert codes(source, "RL107") == [2]
    role_link = '<span role="link" tabindex="0"><img src="x" alt="Next"> Next</span>'
    assert codes(role_link, "RL107") == [1]


# -- RL508 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<button aria-label="Close dialog">Cancel</button>',
        '<a href="/orders/" aria-label="Purchase history">My orders</a>',
        '<input type="submit" value="Go" aria-label="Submit search">',
        '<div role="tab" tabindex="0" aria-label="Settings">Profile</div>',
        '<button aria-label="Next">Next <b>page</b></button>',
    ],
)
def test_label_not_in_name(source):
    assert codes(source, "RL508") == [1]


@pytest.mark.parametrize(
    "source",
    [
        '<button aria-label="Search products">Search</button>',
        '<button aria-label="search  PRODUCTS">Search\n products</button>',
        '<button aria-label="Close">×</button>',
        '<button aria-label="Close">X</button>',
        '<button aria-label="Next">→ →</button>',
        '<button aria-label="Close"><svg aria-hidden="true"></svg></button>',
        '<a href="/" aria-label="Profile">{{ user.name }}</a>',
        '<a href="/" aria-label="{% trans "Profile" %}">Account</a>',
        '<a aria-label="Top">Back</a>',
        '<input type="text" value="Kyiv" aria-label="City">',
        '<input type="submit" value="{{ label }}" aria-label="Send">',
        '<div aria-label="Card">Content</div>',
        '<button {{ attrs }} aria-label="Save">Store</button>',
        '<button aria-label="Save">{% include "icon.html" %}Store</button>',
        '<button aria-label=" ">Store</button>',
    ],
)
def test_label_in_name_ok(source):
    assert codes(source, "RL508") == []


# -- RL706 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<span aria-label="4 out of 5 stars">★★★★☆</span>',
        '<div aria-labelledby="title"></div>',
        '<p aria-label="Note">text</p>',
        '<strong aria-label="Price">$5</strong>',
        '<div role="presentation" aria-label="x"></div>',
        '<ul role="none" aria-label="x"></ul>',
        '<section role="generic" aria-label="x"></section>',
    ],
)
def test_prohibited(source):
    assert codes(source, "RL706") == [1]


@pytest.mark.parametrize(
    "source",
    [
        '<span role="img" aria-label="4 stars">★★★★</span>',
        '<div role="group" aria-label="Shipping"></div>',
        '<div role="region" aria-labelledby="h"></div>',
        '<nav aria-label="Main"></nav>',
        '<section aria-label="News"></section>',
        '<div tabindex="0" aria-label="Map"></div>',
        '<div role="{{ role }}" aria-label="x"></div>',
        '<div role="dailog" aria-label="x"></div>',
        '<div {{ attrs }} aria-label="x"></div>',
        '<div aria-label="">x</div>',
        '<div aria-describedby="help">x</div>',
    ],
)
def test_not_prohibited(source):
    assert codes(source, "RL706") == []
