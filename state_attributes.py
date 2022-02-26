normal_state = {"order": ["type", "tasks_finished", "next_task", "locked", "picked_up", "in_same_cell", "in_m_input", "in_m"],
                "buffer": [],
                "machine": [],
                "agent": []}

smart_state = {"order": [
                        "start", "due_to", "complexity", "type",
                        "time_in_cell", "locked", "picked_up", "processing", "tasks_finished", "remaining_tasks",
                        "next_task", "distance", "in_m", "in_m_input", "in_same_cell"],

               "buffer": ["interface_ingoing", "interface_outgoing"],

               "machine": ["machine_type", "current_setup", "in_setup", "next_setup", "remaining_setup_time", "manufacturing", "failure", "remaining_man_time", "failure_fixed_in"],

               "agent": ["moving", "remaining_moving_time", "next_position", "has_task", "locked_item"]}


#"agent_position"