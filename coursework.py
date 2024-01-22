from constants import CONSTANTS
from random import randint
from typing import List
import datetime as dt
import asyncio
import copy


class Customer:
    def __init__(self, id_: int):
        self.id_ = id_
        self.items = randint(1, CONSTANTS.CUSTOMER_MAX_ITEMS)
        self.is_lottery_winner = randint(1, 100) > 89  # 10% chance of winning the lottery
        self.busy = False
        self.processed = False

    def process(self, lane_id: int, is_regular_lane: bool) -> None:
        """
        Call this function after processing a customer to signal to the store class that the
        customer has been processed
        """

        lane_type = 'regular lane' if is_regular_lane else 'self checkout till'

        print(f'Customer {self.id_} has finalized purchased at {lane_type} {lane_id}. \n')

        self.busy = False
        self.processed = True


class CheckoutLane:
    def __init__(self, max_customers: int, max_items: int = 0, is_open: bool = False):
        # Makes max_items unlimited if argument is not set or a number inferior to 1 is passed
        self.max_items = max_items if max_items > 0 else CONSTANTS.CUSTOMER_MAX_ITEMS + 1
        self.is_open = is_open

        self._max_customers = max_customers
        self._customers: List[Customer] = []

    def add_customer(self, customer: Customer):
        if len(self._customers) >= self._max_customers:
            raise IndexError('Customer limit reached.')

        self._customers.append(customer)

        # Set customer state to busy to avoid reassigning customer to a new lane
        customer.busy = True

    def is_available(self) -> bool:
        return len(self._customers) < self._max_customers and self.is_open

    def get_queue_length(self) -> int:
        return len(self._customers)

    async def process_customers(self) -> None:
        raise NotImplementedError('Implement customer handling.')


class RegularLane(CheckoutLane):
    def __init__(self, lane_id: int, is_open: bool = False):
        self.lane_id = lane_id
        super().__init__(CONSTANTS.REGULAR_LANE_MAX_CUSTOMERS, is_open=is_open)

    def get_processing_time(self) -> int:
        wait_time = 0

        for customer in self._customers:
            wait_time += customer.items * CONSTANTS.REGULAR_LANE_ITEM_PROCESS_SECS  # Time to process items

        return wait_time

    async def process_customers(self) -> None:
        while True:
            for customer in self._customers:
                processing_time = customer.items * CONSTANTS.REGULAR_LANE_ITEM_PROCESS_SECS  # Time to process items

                print(
                    f'Customer {customer.id_} | '
                    f'Being processed at Lane {self.lane_id} | '
                    f'{customer.items} items in basket '
                    f'| {processing_time} secs to process basket | ',
                    end='',
                )

                if customer.is_lottery_winner:
                    print('This customer is a lottery winner! \n')

                else:
                    print('This customer is not a lottery winner. \n')

                await asyncio.sleep(processing_time)

                # Remove customer from customers list after processing all their items
                self._customers.remove(customer)

                # Signal to store customer has been processed
                customer.process(self.lane_id, True)

                # Close lane if no customers are actively using it or waiting in line for it
                if len(self._customers) == 0:
                    self.is_open = False

                    curr_time = dt.datetime.now().time().strftime('%H:%M:%S')

                    print(f'Lane {self.lane_id} has been closed ({curr_time}). \n')

            # Wait the minimum amount of time for an item to be processed
            # so that the event loop can pass control to other functions
            await asyncio.sleep(CONSTANTS.REGULAR_LANE_ITEM_PROCESS_SECS)


class SelfCheckoutTill:
    def __init__(self, till_id: int, busy: bool = False):
        self.till_id = till_id
        self.busy = busy

    async def process_customer(self, customer: Customer, customer_list: List[Customer]) -> None:
        self.busy = True

        processing_time = customer.items * CONSTANTS.SELF_CHECKOUT_ITEM_PROCESS_SECS  # Time to process items

        print(
            f'Customer {customer.id_} | '
            f'Using Self checkout lane at till {self.till_id} | '
            f'{customer.items} items in basket | '
            f'{processing_time} secs to process basket | ',
            end='',
        )

        if customer.is_lottery_winner:
            print('This customer is a lottery winner! \n')

        else:
            print('This customer is not a lottery winner. \n')

        await asyncio.sleep(processing_time)

        # Remove customer from self-checkout customer list
        customer_list.remove(customer)

        # Signal to store that the customer has been processed
        customer.process(self.till_id, False)

        self.busy = False

    def get_queue_length(self) -> int:
        return int(self.busy)


class SelfCheckoutLane(CheckoutLane):
    def __init__(self, is_open: bool = True):
        self.tills = [SelfCheckoutTill(i) for i in range(1, CONSTANTS.SELF_CHECKOUT_TILLS + 1)]

        super().__init__(
            CONSTANTS.SELF_CHECKOUT_MAX_CUSTOMERS,
            CONSTANTS.SELF_CHECKOUT_MAX_ITEMS,
            is_open
        )

    def get_processing_time(self) -> int:
        # We add 1 to the length so that we can determine the exact point a self-checkout till becomes available
        remaining_customers = len(self._customers) + 1 - CONSTANTS.SELF_CHECKOUT_TILLS

        customers_copy = copy.deepcopy(self._customers)

        time_elapsed = 0

        if len(customers_copy) < CONSTANTS.SELF_CHECKOUT_TILLS:
            return time_elapsed

        while len(customers_copy) > remaining_customers:
            time_elapsed += CONSTANTS.SELF_CHECKOUT_ITEM_PROCESS_SECS

            for customer in customers_copy:
                if customer.items == 0:
                    customers_copy.remove(customer)

                    continue

                customer.items -= 1

        return time_elapsed

    async def process_customers(self) -> None:
        while True:
            tasks = []

            for customer in self._customers:
                till = self._get_available_till()

                tasks.append(till.process_customer(customer, self._customers))

            if len(tasks) > 0:
                await asyncio.gather(*tasks)

            await asyncio.sleep(CONSTANTS.SELF_CHECKOUT_ITEM_PROCESS_SECS)

    def _get_available_till(self) -> SelfCheckoutTill:
        while True:
            for till in self.tills:
                if till.busy:
                    continue

                # Set till to busy to avoid setting multiple customers on same till
                till.busy = True

                return till


class Store:
    def __init__(self, regular_lanes: List[RegularLane], self_checkout_lane: SelfCheckoutLane):
        self._regular_lanes = regular_lanes
        self._self_checkout_lane = self_checkout_lane

        self._lanes = [*regular_lanes, self_checkout_lane]
        self._customers = [Customer(i) for i in range(1, CONSTANTS.STARTING_CUSTOMERS + 1)]
        self._customer_count = 0 + len(self._customers)
        self._generated_waves = 0

    async def start_simulation(self) -> None:
        # Run customer assignment, generation, and reporting concurrently,
        # alongside customer processing

        try:
            await asyncio.gather(
                self._generate_and_assign_customers(),
                self._check_customers(),
                self._handle_reports(),
                *[lane.process_customers() for lane in self._lanes],
            )

        # Add exception handling for SystemExit to avoid ugly exception on invoking exit(0)
        except SystemExit:
            pass

    async def _generate_and_assign_customers(self) -> None:
        new_customer_amount = 0

        for _ in range(CONSTANTS.CUSTOMER_WAVES):
            # Customer lane assignment logic
            self._assign_customers()

            await asyncio.sleep(CONSTANTS.CUSTOMER_WAVE_INTERVAL_SECS)

            # Generate up to 5 new customers
            new_customers = randint(1, CONSTANTS.MAX_NEW_CUSTOMERS_PER_WAVE)

            new_customer_amount += new_customers

            # Skip iteration if amount of new customers would make simulation go over max customer limit
            if len(self._customers) + new_customers > CONSTANTS.MAX_CUSTOMERS:
                continue

            # previous_customer_id = x + CONSTANTS.STARTING_CUSTOMERS

            # Add a random amount of customers to simulation (Up to 5 a time)
            self._customers.extend([Customer(i + 1 + self._customer_count) for i in range(new_customers)])

            self._customer_count += new_customers
          
            print(f'{new_customers} new customer(s) have arrived. \n')

            self._generated_waves += 1

        self._assign_customers()

    def _assign_customers(self) -> None:
        for customer in self._customers:
            if customer.busy:
                continue

            is_self_checkout_eligible = customer.items <= CONSTANTS.SELF_CHECKOUT_MAX_ITEMS

            lane = self._get_best_lane(include_self_checkout=is_self_checkout_eligible)

            lane.add_customer(customer)

    async def _check_customers(self) -> None:
        while True:
            for customer in self._customers:
                if customer.processed:
                    self._customers.remove(customer)

                    continue

            # Check to see which customers have been processed every second
            await asyncio.sleep(1)

    async def _handle_reports(self) -> None:
        # Wait 1 second on the first simulation round for all customers to be fully assigned
        await asyncio.sleep(1)

        while len(self._customers) > 0 or self._generated_waves < CONSTANTS.CUSTOMER_WAVES:
            self._generate_report()

            await asyncio.sleep(CONSTANTS.REPORT_INTERVAL_SECS)

        # Generate final report before terminating simulation
        self._generate_report()

        print(f'No more customers are in the store, {self._customer_count} customers have been processed and simulation has finished.')

        exit(0)

    def _generate_report(self) -> None:
        sim_time = dt.datetime.now().time().strftime('%H:%M:%S')

        print(f'----------- START OF REPORT ({sim_time}) ----------- \n')

        print(f'Amount of customers: {len(self._customers)} \n')

        for lane in self._lanes:
            if isinstance(lane, SelfCheckoutLane):
                print(f'Self check out lanes -> {self._gen_star_text(lane.get_queue_length())} \n')

                for till in lane.tills:
                    print(f'Self check out till {till.till_id} -> {self._gen_star_text(till.get_queue_length())} \n')

                continue

            print(f'Regular lane {lane.lane_id} -> {self._gen_star_text(lane.get_queue_length(), not lane.is_open)} \n')

        print(f'----------- END OF REPORT ({sim_time}) ----------- \n')

    def _get_best_lane(self, *, include_self_checkout: bool = True) -> CheckoutLane:
        lanes = self._lanes if include_self_checkout else self._regular_lanes

        # Get available lanes
        available_lanes = list(filter(lambda lane: lane.is_available(), lanes))

        # If there are no available lanes, open a new one
        if len(available_lanes) == 0:
            for new_lane in lanes:
                if not new_lane.is_open:
                    new_lane.is_open = True

                    curr_time = dt.datetime.now().time().strftime('%H:%M:%S')

                    print(f'Lane {new_lane.lane_id} has been opened ({curr_time}). \n')

                    return new_lane

        # Get lane with the lowest wait/processing time
        return min(available_lanes, key=lambda lane: lane.get_processing_time())

    @staticmethod
    def _gen_star_text(amount: int, is_closed: bool = False) -> str:
        empty_text = 'Closed' if is_closed else 'Empty'

        return ' '.join(['*' for _ in range(amount)]) if amount > 0 else empty_text


if __name__ == '__main__':
    store = Store(
        [RegularLane(1, is_open=True), *[RegularLane(i) for i in range(2, 6)]],
        SelfCheckoutLane()
    )

    asyncio.run(store.start_simulation())
