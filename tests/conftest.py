"""Shared pytest fixtures — isolated data directory and database per test session."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_environment():
    tmp = Path(tempfile.mkdtemp(prefix="examgen-tests-"))
    os.environ["EXAMGEN_DATA_DIR"] = str(tmp)
    os.environ["EXAMGEN_DATABASE_URL"] = f"sqlite:///{tmp / 'test.db'}"
    os.environ["EXAMGEN_SECRET_KEY"] = "test-secret-key-not-for-production-use-only"
    os.environ["EXAMGEN_LLM_API_KEY"] = ""

    from examgen.config import reset_settings
    from examgen.db import init_db, reset_engine

    reset_settings()
    reset_engine()
    init_db()
    yield tmp
    reset_engine()
    reset_settings()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from examgen.api.app import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def auth(client):
    """Register a fresh student and return an authorised headers dict."""
    import uuid

    email = f"student-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/auth/register", json={
        "email": email, "password": "correct-horse-battery", "display_name": "Test Student"})
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_text_document() -> bytes:
    """A small, realistic coursework excerpt used across the tests."""
    return b"""Data Structures and Algorithms - Module Notes

Chapter 1. Algorithm Analysis
An algorithm is a finite sequence of well-defined instructions that transforms
an input into a desired output. Time complexity is defined as the rate at which
the running time of an algorithm grows as the input size increases.
The Big O notation describes the upper bound of an algorithm's growth rate.
Calculate the time complexity of a nested loop where the outer loop runs n times
and the inner loop runs n times: the result is O(n^2).

Chapter 2. Sorting Algorithms
Bubble sort is a comparison-based sorting algorithm that repeatedly steps
through the list and swaps adjacent elements that are in the wrong order.
First compare the first two elements, then swap them if they are out of order,
next move to the next pair, finally repeat until the list is sorted.
Merge sort is a divide and conquer algorithm. The worst case time complexity of
merge sort is O(n log n), which is better than the O(n^2) of bubble sort.
Quicksort is defined as a divide and conquer algorithm that selects a pivot
element and partitions the array around it.

Chapter 3. Data Structures
A stack is a linear data structure that follows the last in first out principle.
A queue is a linear data structure that follows the first in first out principle.
A binary search tree is a tree data structure where each node has at most two
children and the left child is smaller than the parent while the right child is
greater. A hash table is a data structure that maps keys to values using a hash
function. The load factor is defined as the number of entries divided by the
number of buckets.

Chapter 4. Graph Algorithms
A graph is a set of vertices connected by edges. Dijkstra's algorithm finds the
shortest path from a source vertex to all other vertices in a weighted graph.
Breadth first search explores a graph level by level using a queue. Depth first
search explores as far as possible along each branch before backtracking.
The time complexity of breadth first search is O(V + E).

Chapter 5. Algorithm Design Techniques
Dynamic programming is defined as a method for solving complex problems by
breaking them into overlapping subproblems and storing the results.
Greedy algorithms make the locally optimal choice at each step. A graph of the
running time against input size can be plotted to compare the growth rates of
different algorithms. The gradient of that graph indicates the growth rate.
"""


def make_previous_paper() -> bytes:
    return b"""CS201 Data Structures - Previous Examination Paper

Question 1
Define the term algorithm and state two properties of a good algorithm.

Question 2
Calculate the time complexity of the following loop and explain your reasoning.

Question 3
Compare merge sort and bubble sort with reference to their worst case time
complexity and their practical performance on large datasets.

Question 4
Draw the entity relationship diagram for a student records system and label the
cardinality of each relationship.
"""
