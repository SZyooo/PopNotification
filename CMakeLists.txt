cmake_minimum_required(VERSION 3.20)

project(pop-notify)

# This project has migrated to Python.
# Run: python main.py

add_custom_target(run
    COMMAND python main.py
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Launch BubbleMind (Python + tkinter)"
)
