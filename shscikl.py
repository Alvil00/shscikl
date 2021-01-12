#coding:utf-8
import abc
import sys
import argparse
import collections
import weakref
import functools
import re

# Interfaces
class CommonInterface(metaclass=abc.ABCMeta):
	def __init__(self, name, description):
		self._name = name
		self._description = description
		
	@property
	def name(self):
		return self._name
	
	@property
	def description(self):
		return self._description
	
	# if this method has overloaded in heirs than means that class stop to be an interface and become class
	@abc.abstractmethod
	def _dummy(self):
		pass

class RegimeClassPrototype(collections.UserList, CommonInterface, metaclass=abc.ABCMeta):
	
	def __init__(self, name, description, map_, *members):
		super(collections.UserList, self).__init__(name, description)
		super().__init__(initlist=members)
		if map_ is not None:
			self._map = weakref.ref(map_)
		else:
			self._map = None
	
	@staticmethod
	def _separte_line_data(line):
		data = line.strip().split('"')
		if len(data) == 2:
			description = ""
		else:
			description = data[1]
		name = data[0].strip()
		members = data[-1].strip().split()
		return name, description, members
	
	
	@classmethod
	def parse(cls, line, map_=None):
		name, description, members = cls._separte_line_data(line)
		return cls(name, description, map_, *members)
	
	@property
	def map_(self):
		if self._map is None:
			return None
		else:
			return self._map()
	
	
class RegimeContainerClassPrototype(collections.UserDict, CommonInterface, metaclass=abc.ABCMeta):
	
	def __init__(self, name, description, **members):
		super(collections.UserDict, self).__init__(name, description)
		super().__init__()

	

# Maps
class RegimeMap(RegimeContainerClassPrototype):
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	@staticmethod
	def sum_reg(rorig, radd, count=1):
		for i in rorig.keys():
			rorig[i] += radd[i] * count
	
	def _dummy(self):
		pass

class BlockMap(RegimeContainerClassPrototype):
	
	def __init__(self, *args, **kwargs):
		self._rmap = weakref.ref(kwargs.pop('rmap'))
		super().__init__(*args, **kwargs)
	
	@property
	def rmap(self):
		return self._rmap()
	
	def _dummy(self):
		pass

# Units
class Regime(RegimeClassPrototype):
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if self.map_ is not None:
			self.map_[self.name] = self
	
	def _dummy(self):
		pass

class Block(RegimeClassPrototype):
	
	def __init__(self, *args, **kwargs):
		self._count = kwargs.pop('count')
		super().__init__(*args, **kwargs)
		if self.map_ is not None:
			self.map_[self.name] = self
		
	@property
	def count(self):
		return self._count
	
	@classmethod
	def parse(cls, line, map_=None):
		name, description, members = cls._separte_line_data(line)
		TOKENS ={
			"OPEN_BRACKET"  :r"\(",
			"CLOSE_BRACKET" :r"\)",
			"REGIME_UNIT"   :r"[\w/]*[a-zA-z_/]+[\w/]*",
			"COUNT_UNIT"    :r"\d+\b"
		}
		PATTERN = "|".join(["(?P<{name}>{pattern})".format(name=n, pattern=v) for n, v in TOKENS.items()])
		incorp_level = 0
		close_brackets = 0
		stack = [[],]
		namestack = [name,]
		count_flag = False
		current_regimeseq = None
		current_name = None
		for token in re.finditer(PATTERN, ' '.join(members)):
			token_name = token.lastgroup
			value = token.group(token_name)
			if incorp_level < 0:
				raise ValueError
			if count_flag:
				if token_name == "COUNT_UNIT":
					n = int(value)
				else:
					n = 1
				cls(current_name, description, map_, *current_regimeseq, count=n)
				count_flag = False
				if token_name == "COUNT_UNIT":
					continue
			if token_name=="OPEN_BRACKET":
				incorp_level += 1
				stack.append([])
				namestack.append(namestack[-1] + "/1")
				while True:
					if map_.get(namestack[-1]) is not None:
							dtch = namestack[-1].rsplit('/', 1)
							namestack[-1] = "/".join([dtch[0], str(int(dtch[1]) + 1)])
					else:
						break
			elif token_name == "CLOSE_BRACKET":
				incorp_level -= 1
				close_brackets += 1
				current_regimeseq = stack.pop()
				current_name = namestack.pop()
				stack[-1].append(current_name)
				count_flag = True
			elif token_name == "REGIME_UNIT":
				stack[-1].append(value)
			elif token_name == "COUNT_UNIT":
				raise ValueError
		if incorp_level != 0:
			raise ValueError
		if count_flag:
			cls(current_name, description, map_, *current_regimeseq, count=1)
			count_flag = False
		if len(stack[0]) == 1 and close_brackets == 1:
			map_[name] = map_.pop(name + "/1")
			return map_[name]
		else:
			return cls(name, description, map_, *stack[0], count=1)
	
	def walk(self):	
		result = self.map_.rmap.keys()
		result = dict(zip(result, [0,]*len(result)))
		for i in self:
			if i in result.keys():
				result[i] += self._count
			elif i in self.map_.keys():
				RegimeMap.sum_reg(result, self.map_[i].walk(), self._count)
		return result
	
	def _dummy(self):
		pass

class History(RegimeClassPrototype):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
	
	def _dummy(self):
		pass

# Script Manager
class Manager:
	
	# Manager context tokens
	REGIMS_TOKEN =  "#regims"
	BLOCKS_TOKEN =  "#blocks"
	HISTORY_TOKEN = "#HIST"
	
	def __init__(self, blocks_map, regimes_map):
		self._history = None
		self._block_map = blocks_map
		self._regime_map = regimes_map
		self._context_class = None
		self.reload_commands()
		
	def reload_commands(self):
		self._CONTEXT = \
		{
			self.REGIMS_TOKEN : functools.partial(Regime.parse, map_=self._regime_map),
			self.BLOCKS_TOKEN : functools.partial(Block.parse,  map_=self._block_map ),
			self.HISTORY_TOKEN: History.parse
		}
	
	def __call__(self, line):
		try:				# Try to change context
			context_operation = line.strip().split()[0]
			self.change_context(context_operation)
		except IndexError: 	# It is space line
			return None
		except KeyError:	# It is RegimeUnit line
			if self._context_class is not None:
				res_ = self._context_class(line)
				if isinstance(res_, History):
					self._history = res_
			return None

	@property
	def history(self):
		return self._history
		
	def change_context(self, context_line):
		self._context_class = self._CONTEXT[context_line]
	
	def calc_sum(self):
		result = self._regime_map.keys()
		result = dict(zip(result, [0,]*len(result)))
		if self.history is None:
			print("Error: Can't find history!", file=sys.stderr)
			return None
		try:
			for hb in self.history:
				RegimeMap.sum_reg(result, self._block_map[hb].walk())
			return result
		except RecursionError:
			print("Error: You have a recursion in your history!", file=sys.stderr)
			return None
		except KeyError as ke:
			print("Error: You have an undefined block into you history:{}".format(ke.args[0]), file=sys.stderr)
			return None

	def print_regime_calc_sum(self):
		info = self.calc_sum()
		if info is not None:
			for item, count in info.items():
				print("{:>6} : {:^20} : {:<7}".format(item, self._regime_map[item].description.strip(), count))
	
	def read_file(self, file, encoding):
		with open(file, 'r', encoding=encoding) as file:
			for line in file:
				self(line)
				
def parse_args(args):
	a = argparse.ArgumentParser("Calculate frequency of each regime in history")
	a.add_argument('file', help="File which contains history")
	a.add_argument('-e', '--encoding', help="Set history file encoding", choices=("utf-8", "cp866", "cp1251"), default="utf-8", dest='encoding')
	ra = a.parse_args(args)
	return ra
	
def main():
	args = parse_args(sys.argv[1:])
	rm = RegimeMap(name='regims', description=None)
	bm = BlockMap(name='blocks',  description=None, rmap=rm)
	manager = Manager(bm, rm)
	manager.read_file(args.file, args.encoding)
	manager.print_regime_calc_sum()

if __name__=="__main__":
	main()