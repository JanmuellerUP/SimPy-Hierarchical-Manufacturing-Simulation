"""Copyright 2022 Jannis Müller/ janmueller@uni-potsdam.de

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License."""


def consecutive_performable_tasks(next_tasks, performable_tasks):

    performable_tasks = [task for (task, amount) in performable_tasks if amount > 0]

    next_tasks = [task in performable_tasks for task in next_tasks]

    if False in next_tasks:
        return next_tasks.index(False)
    else:
        return len(next_tasks)
