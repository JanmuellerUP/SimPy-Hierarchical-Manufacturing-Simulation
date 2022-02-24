def consecutive_performable_tasks(next_tasks, performable_tasks):

    performable_tasks = [task for (task, amount) in performable_tasks if amount > 0]

    next_tasks = [task in performable_tasks for task in next_tasks]

    if False in next_tasks:
        return next_tasks.index(False)
    else:
        return len(next_tasks)
